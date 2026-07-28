from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from modules.magnetic.constants import BASE_TOTAL_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.exceptions import MagneticReadError, MagneticSchemaError
from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticLineType, MagneticSurveyType
from modules.magnetic.readers.base_reader import MagneticFormatReader, ReaderOptions


_SENSOR_RE = re.compile(
    r"^!\s*(?P<field>[+-]?\d+(?:\.\d+)?)"
    r"(?P<validation>[_*])"
    r"@(?P<counter>\d+)"
    r"s(?P<sensitivity>\d+)"
    r"(?P<suffix>(?:,.*)?)$"
)


@dataclass(frozen=True)
class _SensorSample:
    field_nt: float
    validation: str
    counter: int
    sensitivity: int
    bno_heading_deg: float
    mx: float
    my: float
    mz: float


@dataclass(frozen=True)
class _GpsFix:
    timestamp: datetime
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    hdop: float
    satellites: float
    fix_quality: float
    heading_deg: float
    pps_valid: bool


class BulucuAcquisitionReader(MagneticFormatReader):
    """Reader for Bulucu acquisition logger files.

    The format is event based rather than a rectangular CSV table.  Scalar
    magnetometer records start with ``!`` and GPS fixes start with ``@GPS``.
    The logger header explicitly declares the field order and sensor units.

    Sensor timestamps are not written by the logger.  This reader therefore
    georeferences sensor events by their FIFO order between adjacent GPS fixes.
    The inferred timing method and any edge extrapolation are recorded in
    dataset metadata and quality flags instead of being hidden from QC.
    """

    SIGNATURES = ("bulucu_acq_header=", "gps_prefix=@gps", "sensor_prefix=!")
    EXTENSIONS = {".txt", ".log", ".dat"}

    def can_read(self, path: Path) -> bool:
        if path.suffix.lower() not in self.EXTENSIONS or not path.is_file():
            return False
        try:
            with path.open("r", encoding="utf-8-sig", errors="ignore") as stream:
                prefix = stream.read(8192).lower()
        except OSError:
            return False
        return "bulucu_acq_header=" in prefix and "sensor_value_name=mag_nt" in prefix

    def inspect(self, path: Path, options: ReaderOptions | None = None) -> dict[str, Any]:
        options = options or ReaderOptions()
        header, counters, gps_preview, movement = self._scan(path, preview_limit=5)
        source_crs = self._source_crs(options)
        recommended_working_crs = self._recommended_utm_crs(gps_preview or movement.get("representative_fix"))
        classification = self._classify_acquisition(movement)
        return {
            "path": str(path),
            "reader": type(self).__name__,
            "format": f"Bulucu Acquisition Log v{header.get('bulucu_acq_header', '?')}",
            "format_id": "bulucu_acquisition_log",
            "header": header,
            "sensor_serial_number": header.get("sensor_serial"),
            "logger_serial": header.get("logger_serial"),
            "log_name": header.get("log_name", path.stem),
            "remark": header.get("remark", ""),
            "magnetic_channel": header.get("sensor_value_name", "mag_nt"),
            "magnetic_units": header.get("sensor_value_unit", "nT"),
            "coordinate_type": "latitude_longitude",
            "detected_crs": source_crs,
            "crs_confidence": "high",
            "recommended_working_crs": recommended_working_crs,
            "gps_rate_hz": self._float_or_none(header.get("gps_rate_hz")),
            "gps_fields": [value.strip() for value in header.get("gps_fields", "").split(",") if value.strip()],
            "record_counts": counters,
            "preview": gps_preview[:5],
            "movement": movement,
            "suggested_acquisition_classification": classification,
            "suggested_primary_use": "stationary/base QC" if classification == "stationary" else "rover survey QC",
            "required_missing": (),
            "confidence": 1.0,
            "mapping": {
                "total_field": "!<mag_nt>",
                "timestamp": "@GPS gps_iso_utc / inferred FIFO sensor time",
                "x": "@GPS lon_deg",
                "y": "@GPS lat_deg",
                "elevation": "@GPS alt_m",
            },
        }

    def read(self, path: Path, options: ReaderOptions | None = None) -> MagneticDataset:
        options = options or ReaderOptions()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size == 0:
            raise MagneticReadError("Magnetic source file is empty")

        header: dict[str, str] = {}
        output: dict[str, list[Any]] = {
            "timestamp": [],
            "field": [],
            "validation_bad": [],
            "sensor_counter": [],
            "sensitivity": [],
            "bno_heading": [],
            "bno_mx": [],
            "bno_my": [],
            "bno_mz": [],
            "longitude": [],
            "latitude": [],
            "altitude": [],
            "hdop": [],
            "satellites": [],
            "fix_quality": [],
            "gps_heading": [],
            "pps_valid": [],
            "georef_edge_inferred": [],
        }

        previous_gps: _GpsFix | None = None
        pending_sensors: list[_SensorSample] = []
        malformed_sensor = 0
        malformed_gps = 0
        ignored_events = 0
        gps_count = 0
        sensor_count = 0

        with path.open("r", encoding=options.encoding, errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    self._consume_header_line(line, header)
                    continue
                if line.startswith("!"):
                    sensor_count += 1
                    sample = self._parse_sensor(line)
                    if sample is None:
                        malformed_sensor += 1
                    else:
                        pending_sensors.append(sample)
                    continue
                if line.startswith("@GPS"):
                    gps_count += 1
                    gps = self._parse_gps(line)
                    if gps is None:
                        malformed_gps += 1
                        continue
                    self._emit_pending(
                        pending_sensors,
                        previous_gps,
                        gps,
                        output,
                        header=header,
                        edge="start" if previous_gps is None else None,
                    )
                    pending_sensors.clear()
                    previous_gps = gps
                    continue
                ignored_events += 1

        if pending_sensors:
            self._emit_pending(
                pending_sensors,
                previous_gps,
                None,
                output,
                header=header,
                edge="end",
            )

        if not output["field"]:
            raise MagneticReadError("No valid scalar magnetic sensor records could be georeferenced from the Bulucu log")

        timestamps = np.asarray(output["timestamp"], dtype="datetime64[ms]")
        field = np.asarray(output["field"], dtype=float)
        longitude = np.asarray(output["longitude"], dtype=float)
        latitude = np.asarray(output["latitude"], dtype=float)
        altitude = np.asarray(output["altitude"], dtype=float)

        source_crs = self._source_crs(options)
        movement = self._movement_summary(longitude, latitude, timestamps)
        classification = self._classify_acquisition(movement)
        recommended_working_crs = self._recommended_utm_crs_from_arrays(longitude, latitude)

        primary_channel = BASE_TOTAL_FIELD if options.role == MagneticDataRole.BASE else RAW_TOTAL_FIELD
        channels: dict[str, np.ndarray] = {
            primary_channel: field,
            "sensor_sensitivity": np.asarray(output["sensitivity"], dtype=float),
            "sensor_counter": np.asarray(output["sensor_counter"], dtype=float),
            "bno_heading_deg": np.asarray(output["bno_heading"], dtype=float),
            "bno_mx": np.asarray(output["bno_mx"], dtype=float),
            "bno_my": np.asarray(output["bno_my"], dtype=float),
            "bno_mz": np.asarray(output["bno_mz"], dtype=float),
            "gps_hdop": np.asarray(output["hdop"], dtype=float),
            "gps_quality": np.asarray(output["fix_quality"], dtype=float),
            "satellites": np.asarray(output["satellites"], dtype=float),
            "gps_heading_deg": np.asarray(output["gps_heading"], dtype=float),
            "heading": np.asarray(output["gps_heading"], dtype=float),
            "gps_pps_valid": np.asarray(output["pps_valid"], dtype=float),
        }

        quality_flags = {
            "sensor_validation_bad": np.asarray(output["validation_bad"], dtype=bool),
            "gps_invalid_fix": np.asarray(output["fix_quality"], dtype=float) <= 0,
            "gps_pps_missing": np.asarray(output["pps_valid"], dtype=float) < 0.5,
            "georef_edge_inferred": np.asarray(output["georef_edge_inferred"], dtype=bool),
        }

        n = field.size
        if options.role == MagneticDataRole.BASE:
            line_id = np.full(n, "", dtype=object)
            line_type = np.full(n, MagneticLineType.BASE.value, dtype=object)
            survey_type = MagneticSurveyType.BASE_STATION
        else:
            # A stationary acquisition should not be forced through line-spacing,
            # straightness and tie-line tests.  Leave line IDs empty so those
            # stages correctly report SKIPPED rather than false failures.
            if classification == "stationary":
                line_id = np.full(n, "", dtype=object)
                line_type = np.full(n, MagneticLineType.UNKNOWN.value, dtype=object)
            else:
                line_name = header.get("log_name", path.stem)
                line_id = np.full(n, line_name, dtype=object)
                line_type = np.full(n, MagneticLineType.TRAVERSE.value, dtype=object)
            survey_type = options.survey_type

        metadata = dict(options.metadata)
        metadata.update(
            {
                "reader": type(self).__name__,
                "format_id": "bulucu_acquisition_log",
                "format_version": header.get("bulucu_acq_header"),
                "log_name": header.get("log_name", path.stem),
                "remark": header.get("remark", ""),
                "sensor_serial_number": header.get("sensor_serial"),
                "logger_serial": header.get("logger_serial"),
                "sensor_mode": header.get("sensor_mode", "scalar"),
                "sensor_value_name": header.get("sensor_value_name", "mag_nt"),
                "sensor_value_unit": header.get("sensor_value_unit", "nT"),
                "gps_rate_hz": self._float_or_none(header.get("gps_rate_hz")),
                "gps_fields": header.get("gps_fields"),
                "event_order": header.get("event_order", "fifo_arrival"),
                "sensor_timestamp_enabled": header.get("sensor_timestamp_enabled", "no"),
                "timestamp_source": "GPS event-order interpolation (sensor has no native timestamp)",
                "georeferencing_method": "FIFO sensor events interpolated between adjacent GPS fixes",
                "source_coordinate_type": "latitude_longitude",
                "source_crs_detected": "EPSG:4326",
                "source_crs_assumption": "GPS latitude/longitude interpreted as WGS84",
                "recommended_working_crs": recommended_working_crs,
                "acquisition_classification": classification,
                "movement_summary": movement,
                "source_header": header,
                "source_sensor_records": sensor_count,
                "source_gps_records": gps_count,
                "imported_records": int(n),
                "malformed_sensor_records": malformed_sensor,
                "malformed_gps_records": malformed_gps,
                "ignored_event_records": ignored_events,
                "column_mapping": {
                    "total_field": "sensor !mag_nt",
                    "timestamp": "GPS/inferred",
                    "x": "lon_deg",
                    "y": "lat_deg",
                    "elevation": "alt_m",
                },
            }
        )

        return MagneticDataset(
            source_path=path,
            role=options.role,
            survey_type=survey_type,
            timestamps=timestamps,
            channels=channels,
            x=longitude,
            y=latitude,
            elevation=altitude,
            line_id=line_id,
            station_id=np.asarray([str(index + 1) for index in range(n)], dtype=object),
            line_type=line_type,
            metadata=metadata,
            crs=source_crs,
            coordinate_units="degrees",
            magnetic_units=header.get("sensor_value_unit", options.magnetic_units or "nT"),
            quality_flags=quality_flags,
        )

    def _scan(
        self,
        path: Path,
        *,
        preview_limit: int,
    ) -> tuple[dict[str, str], dict[str, int], list[dict[str, Any]], dict[str, Any]]:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size == 0:
            raise MagneticReadError("Magnetic source file is empty")
        header: dict[str, str] = {}
        counters = {"sensor": 0, "gps": 0, "malformed_sensor": 0, "malformed_gps": 0}
        preview: list[dict[str, Any]] = []
        lons: list[float] = []
        lats: list[float] = []
        gps_times: list[np.datetime64] = []
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    self._consume_header_line(line, header)
                    continue
                if line.startswith("!"):
                    counters["sensor"] += 1
                    if self._parse_sensor(line) is None:
                        counters["malformed_sensor"] += 1
                    continue
                if line.startswith("@GPS"):
                    counters["gps"] += 1
                    fix = self._parse_gps(line)
                    if fix is None:
                        counters["malformed_gps"] += 1
                        continue
                    lons.append(fix.longitude_deg)
                    lats.append(fix.latitude_deg)
                    gps_times.append(np.datetime64(fix.timestamp.replace(tzinfo=None), "ms"))
                    if len(preview) < preview_limit:
                        preview.append(
                            {
                                "timestamp": fix.timestamp.isoformat(),
                                "latitude_deg": fix.latitude_deg,
                                "longitude_deg": fix.longitude_deg,
                                "altitude_m": fix.altitude_m,
                                "hdop": fix.hdop,
                                "satellites": fix.satellites,
                                "fix_quality": fix.fix_quality,
                            }
                        )
        movement = self._movement_summary(
            np.asarray(lons, dtype=float),
            np.asarray(lats, dtype=float),
            np.asarray(gps_times, dtype="datetime64[ms]"),
        )
        if preview:
            movement["representative_fix"] = preview[len(preview) // 2]
        return header, counters, preview, movement

    @staticmethod
    def _consume_header_line(line: str, header: dict[str, str]) -> None:
        text = line[1:].strip()
        if "=" not in text:
            return
        key, value = text.split("=", 1)
        key = key.strip()
        if key:
            header[key] = value.strip()

    @staticmethod
    def _parse_sensor(line: str) -> _SensorSample | None:
        match = _SENSOR_RE.match(line)
        if not match:
            return None
        suffix: dict[str, str] = {}
        suffix_text = match.group("suffix").lstrip(",")
        if suffix_text:
            for token in suffix_text.split(","):
                if "=" in token:
                    key, value = token.split("=", 1)
                    suffix[key.strip().lower()] = value.strip()
        return _SensorSample(
            field_nt=float(match.group("field")),
            validation=match.group("validation"),
            counter=int(match.group("counter")),
            sensitivity=int(match.group("sensitivity")),
            bno_heading_deg=BulucuAcquisitionReader._safe_float(suffix.get("bno")),
            mx=BulucuAcquisitionReader._safe_float(suffix.get("mx")),
            my=BulucuAcquisitionReader._safe_float(suffix.get("my")),
            mz=BulucuAcquisitionReader._safe_float(suffix.get("mz")),
        )

    @staticmethod
    def _parse_gps(line: str) -> _GpsFix | None:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 10 or parts[0] != "@GPS":
            return None
        try:
            pps = parts[1].split("=", 1)[1].strip().upper() if "=" in parts[1] else parts[1].upper()
            timestamp = datetime.fromisoformat(parts[2].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
            return _GpsFix(
                timestamp=timestamp,
                latitude_deg=float(parts[3]),
                longitude_deg=float(parts[4]),
                altitude_m=float(parts[5]),
                hdop=float(parts[6]),
                satellites=float(parts[7]),
                fix_quality=float(parts[8]),
                heading_deg=float(parts[9]),
                pps_valid=pps in {"Y", "YES", "1", "TRUE"},
            )
        except (ValueError, IndexError):
            return None

    @classmethod
    def _emit_pending(
        cls,
        pending: list[_SensorSample],
        previous_gps: _GpsFix | None,
        current_gps: _GpsFix | None,
        output: dict[str, list[Any]],
        *,
        header: dict[str, str],
        edge: str | None,
    ) -> None:
        if not pending:
            return

        gps_rate = cls._safe_float(header.get("gps_rate_hz"), default=1.0)
        interval_s = 1.0 / gps_rate if gps_rate and gps_rate > 0 else 1.0

        if previous_gps is not None and current_gps is not None:
            start = previous_gps
            end = current_gps
            fractions = [(index + 1) / (len(pending) + 1) for index in range(len(pending))]
            inferred_edge = False
        elif current_gps is not None:
            # The first sensor event can precede the first GPS sentence.  Use
            # logger start_iso where available, otherwise back-project one GPS
            # interval.  Preserve the inference flag for QC/reporting.
            start_time = cls._parse_iso(header.get("start_iso")) or (current_gps.timestamp - timedelta(seconds=interval_s))
            start = _GpsFix(
                start_time,
                current_gps.latitude_deg,
                current_gps.longitude_deg,
                current_gps.altitude_m,
                current_gps.hdop,
                current_gps.satellites,
                current_gps.fix_quality,
                current_gps.heading_deg,
                current_gps.pps_valid,
            )
            end = current_gps
            fractions = [(index + 0.5) / max(len(pending), 1) for index in range(len(pending))]
            inferred_edge = True
        elif previous_gps is not None:
            stop_time = cls._parse_iso(header.get("stop_iso"))
            if stop_time is None or stop_time <= previous_gps.timestamp:
                stop_time = previous_gps.timestamp + timedelta(seconds=interval_s * len(pending))
            end = _GpsFix(
                stop_time,
                previous_gps.latitude_deg,
                previous_gps.longitude_deg,
                previous_gps.altitude_m,
                previous_gps.hdop,
                previous_gps.satellites,
                previous_gps.fix_quality,
                previous_gps.heading_deg,
                previous_gps.pps_valid,
            )
            start = previous_gps
            fractions = [(index + 0.5) / max(len(pending), 1) for index in range(len(pending))]
            inferred_edge = True
        else:
            # No GPS at all.  Keep the magnetic measurements with NaT/NaN
            # rather than discarding scientific data; spatial QC will skip.
            start = end = None
            fractions = [0.0] * len(pending)
            inferred_edge = True

        good_char = header.get("sensor_validation_good_char", "_")
        for sample, fraction in zip(pending, fractions):
            if start is None or end is None:
                timestamp = np.datetime64("NaT", "ms")
                lon = lat = alt = hdop = sats = fix = heading = float("nan")
                pps = 0.0
            else:
                timestamp_dt = start.timestamp + (end.timestamp - start.timestamp) * fraction
                timestamp = np.datetime64(timestamp_dt.replace(tzinfo=None), "ms")
                lon = cls._lerp(start.longitude_deg, end.longitude_deg, fraction)
                lat = cls._lerp(start.latitude_deg, end.latitude_deg, fraction)
                alt = cls._lerp(start.altitude_m, end.altitude_m, fraction)
                hdop = cls._lerp(start.hdop, end.hdop, fraction)
                sats = cls._lerp(start.satellites, end.satellites, fraction)
                fix = cls._lerp(start.fix_quality, end.fix_quality, fraction)
                heading = cls._lerp_heading(start.heading_deg, end.heading_deg, fraction)
                pps = 1.0 if (start.pps_valid and end.pps_valid) else 0.0

            output["timestamp"].append(timestamp)
            output["field"].append(sample.field_nt)
            output["validation_bad"].append(sample.validation != good_char)
            output["sensor_counter"].append(sample.counter)
            output["sensitivity"].append(sample.sensitivity)
            output["bno_heading"].append(sample.bno_heading_deg)
            output["bno_mx"].append(sample.mx)
            output["bno_my"].append(sample.my)
            output["bno_mz"].append(sample.mz)
            output["longitude"].append(lon)
            output["latitude"].append(lat)
            output["altitude"].append(alt)
            output["hdop"].append(hdop)
            output["satellites"].append(sats)
            output["fix_quality"].append(fix)
            output["gps_heading"].append(heading)
            output["pps_valid"].append(pps)
            output["georef_edge_inferred"].append(inferred_edge or edge is not None)

    @staticmethod
    def _source_crs(options: ReaderOptions) -> str:
        if not options.crs:
            return "EPSG:4326"
        normalised = options.crs.strip().upper().replace(" ", "")
        if normalised in {"4326", "EPSG:4326", "WGS84", "WGS-84"}:
            return "EPSG:4326"
        raise MagneticSchemaError(
            "This Bulucu file stores GPS latitude/longitude coordinates. "
            "Its source CRS is interpreted as WGS84 / EPSG:4326. Do not assign "
            "a projected EPSG code unless the coordinates are actually transformed."
        )

    @staticmethod
    def _recommended_utm_crs(preview_or_fix: Any) -> str | None:
        if not preview_or_fix:
            return None
        if isinstance(preview_or_fix, list):
            fix = preview_or_fix[len(preview_or_fix) // 2]
        else:
            fix = preview_or_fix
        try:
            lon = float(fix.get("longitude_deg"))
            lat = float(fix.get("latitude_deg"))
        except (AttributeError, TypeError, ValueError):
            return None
        zone = int(math.floor((lon + 180.0) / 6.0) + 1)
        zone = max(1, min(zone, 60))
        epsg = 32600 + zone if lat >= 0 else 32700 + zone
        return f"EPSG:{epsg}"

    @classmethod
    def _recommended_utm_crs_from_arrays(cls, longitude: np.ndarray, latitude: np.ndarray) -> str | None:
        valid = np.isfinite(longitude) & np.isfinite(latitude)
        if not np.any(valid):
            return None
        return cls._recommended_utm_crs(
            {
                "longitude_deg": float(np.nanmedian(longitude[valid])),
                "latitude_deg": float(np.nanmedian(latitude[valid])),
            }
        )

    @staticmethod
    def _movement_summary(longitude: np.ndarray, latitude: np.ndarray, timestamps: np.ndarray) -> dict[str, Any]:
        valid = np.isfinite(longitude) & np.isfinite(latitude)
        if np.count_nonzero(valid) < 2:
            return {
                "valid_gps_records": int(np.count_nonzero(valid)),
                "bounding_diagonal_m": 0.0,
                "net_displacement_m": 0.0,
                "track_length_m": 0.0,
                "median_step_m": 0.0,
                "duration_s": 0.0,
            }
        lon = longitude[valid]
        lat = latitude[valid]
        radius = 6_371_008.8
        lon0 = np.radians(float(np.nanmedian(lon)))
        lat0 = np.radians(float(np.nanmedian(lat)))
        x = radius * (np.radians(lon) - lon0) * np.cos(lat0)
        y = radius * (np.radians(lat) - lat0)
        steps = np.hypot(np.diff(x), np.diff(y))
        bounding_diagonal = float(np.hypot(np.nanmax(x) - np.nanmin(x), np.nanmax(y) - np.nanmin(y)))
        net_displacement = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
        track_length = float(np.nansum(steps))
        median_step = float(np.nanmedian(steps)) if steps.size else 0.0
        duration_s = 0.0
        valid_times = timestamps[~np.isnat(timestamps)] if timestamps.size else np.empty(0, dtype="datetime64[ms]")
        if valid_times.size >= 2:
            duration_s = float((valid_times.max() - valid_times.min()) / np.timedelta64(1, "s"))
        return {
            "valid_gps_records": int(lon.size),
            "bounding_diagonal_m": bounding_diagonal,
            "net_displacement_m": net_displacement,
            "track_length_m": track_length,
            "median_step_m": median_step,
            "p95_step_m": float(np.nanpercentile(steps, 95)) if steps.size else 0.0,
            "duration_s": duration_s,
        }

    @staticmethod
    def _classify_acquisition(movement: dict[str, Any]) -> str:
        duration = float(movement.get("duration_s", 0.0) or 0.0)
        bounding = float(movement.get("bounding_diagonal_m", 0.0) or 0.0)
        net = float(movement.get("net_displacement_m", 0.0) or 0.0)
        median_step = float(movement.get("median_step_m", 0.0) or 0.0)
        # Long-duration records confined to a small footprint with negligible
        # median movement are far more likely to be a base/static acquisition
        # than a traverse. This is a suggestion only; raw data is not altered.
        if duration >= 300.0 and bounding <= 150.0 and net <= 100.0 and median_step <= 0.75:
            return "stationary"
        return "moving"

    @staticmethod
    def _safe_float(value: Any, default: float = float("nan")) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        result = BulucuAcquisitionReader._safe_float(value)
        return result if np.isfinite(result) else None

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _lerp(a: float, b: float, fraction: float) -> float:
        if not np.isfinite(a) and not np.isfinite(b):
            return float("nan")
        if not np.isfinite(a):
            return b
        if not np.isfinite(b):
            return a
        return float(a + (b - a) * fraction)

    @staticmethod
    def _lerp_heading(a: float, b: float, fraction: float) -> float:
        if not np.isfinite(a) or not np.isfinite(b):
            return BulucuAcquisitionReader._lerp(a, b, fraction)
        delta = ((b - a + 180.0) % 360.0) - 180.0
        return float((a + delta * fraction) % 360.0)
