from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from modules.magnetic.constants import BASE_TOTAL_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.exceptions import MagneticReadError, MagneticSchemaError
from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticLineType, MagneticSurveyType
from modules.magnetic.readers.base_reader import MagneticFormatReader, ReaderOptions


_SENSOR_RE = re.compile(
    r"^!\s*(?P<field>[+-]?\d+(?:\.\d+)?)"
    r"(?P<validation>[_*]?)"
    r"(?:@(?P<counter>\d+))?"
    r"(?:s(?P<sensitivity>\d+))?"
    r"(?P<suffix>(?:[,;\s].*)?)$",
    re.IGNORECASE,
)
_KEY_VALUE_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_ /\-]*)\s*[=:]\s*(?P<value>[^,;\s]+)")


@dataclass(frozen=True)
class EnmagSensorSample:
    field_nt: float
    validation: str
    counter: int | None
    sensitivity: float
    bno_heading_deg: float
    mx: float
    my: float
    mz: float
    raw_line: str


@dataclass(frozen=True)
class EnmagGpsFix:
    timestamp: datetime
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    hdop: float
    satellites: float
    fix_quality: float
    heading_deg: float
    pps_valid: bool
    raw_line: str


class EnmagAcquisitionReader(MagneticFormatReader):
    """Native event-log reader for EnMag Data / ENmag field acquisition logs.

    The EnMag utility analysed event style files containing separate GPS records
    (usually ``@GPS``) and scalar magnetic sensor events (``!``).  This reader
    imports those same field logs directly into TGPAssure, georeferencing sensor
    samples by FIFO order between GPS fixes and preserving validation markers,
    BNO heading/vector channels, parse diagnostics and dropped-edge counters.
    """

    EXTENSIONS = {".txt", ".log", ".dat"}
    SIGNATURES = (
        "@gps",
        "gps_prefix=@gps",
        "sensor_prefix=!",
        "enmag data qc",
        "enmag data",
        "enmag",
        "bno",
        "mag_nt",
    )

    def can_read(self, path: Path) -> bool:
        if path.suffix.lower() not in self.EXTENSIONS or not path.is_file():
            return False
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")[:16384].lower()
        except OSError:
            return False
        has_gps = "@gps" in text or "$gpgga" in text or "$gn" in text
        has_sensor = re.search(r"(?m)^\s*!\s*[+-]?\d", text) is not None
        # Strong event-log signal, even when no explicit EnMag header is present.
        if has_gps and has_sensor:
            return True
        return has_sensor and any(signature in text for signature in self.SIGNATURES)

    def inspect(self, path: Path, options: ReaderOptions | None = None) -> dict[str, Any]:
        options = options or ReaderOptions()
        header, counters, preview, movement = self._scan(path, preview_limit=8, encoding=options.encoding)
        source_crs = self._source_crs(options)
        classification = self._classify_acquisition(movement)
        return {
            "path": str(path),
            "reader": type(self).__name__,
            "format": "EnMag event acquisition log",
            "format_id": "enmag_event_acquisition_log",
            "header": header,
            "record_counts": counters,
            "preview": preview,
            "movement": movement,
            "coordinate_type": "latitude_longitude",
            "detected_crs": source_crs,
            "crs_confidence": "high",
            "recommended_working_crs": self._recommended_utm_crs(movement.get("representative_fix")),
            "suggested_acquisition_classification": classification,
            "confidence": 0.95,
            "required_missing": (),
            "mapping": {
                "total_field": "! magnetic sensor event",
                "timestamp": "@GPS event-order interpolation",
                "x": "@GPS longitude",
                "y": "@GPS latitude",
                "elevation": "@GPS altitude",
                "heading": "BNO/gps heading when present",
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
            "validation_marker": [],
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
            "raw_line": [],
        }

        previous_gps: EnmagGpsFix | None = None
        pending_sensors: list[EnmagSensorSample] = []
        counters = {
            "total_records": 0,
            "header_records": 0,
            "gps_records": 0,
            "gps_points": 0,
            "sensor_records": 0,
            "invalid_sensor_records": 0,
            "malformed_gps_records": 0,
            "malformed_sensor_records": 0,
            "inline_event_records": 0,
            "inline_bad_data_events": 0,
            "dropped_pre_gps_sensors": 0,
            "dropped_tail_sensors": 0,
        }

        with path.open("r", encoding=options.encoding, errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                counters["total_records"] += 1
                if self._is_header_line(line):
                    counters["header_records"] += 1
                    self._consume_header_line(line, header)
                    continue
                if line.startswith("!"):
                    counters["sensor_records"] += 1
                    sample = self._parse_sensor(line)
                    if sample is None:
                        counters["malformed_sensor_records"] += 1
                    else:
                        if sample.validation == "*":
                            counters["invalid_sensor_records"] += 1
                        pending_sensors.append(sample)
                    continue
                if line.upper().startswith("@GPS") or line.startswith("$GP") or line.startswith("$GN"):
                    counters["gps_records"] += 1
                    gps = self._parse_gps(line)
                    if gps is None:
                        counters["malformed_gps_records"] += 1
                        continue
                    counters["gps_points"] += 1
                    self._emit_pending(pending_sensors, previous_gps, gps, output, header=header, edge="start" if previous_gps is None else None)
                    if previous_gps is None and pending_sensors:
                        counters["dropped_pre_gps_sensors"] += 0  # Edge samples are retained but flagged.
                    pending_sensors.clear()
                    previous_gps = gps
                    continue
                counters["inline_event_records"] += 1
                if any(token in line.lower() for token in ("bad", "error", "invalid", "reject", "noise")):
                    counters["inline_bad_data_events"] += 1

        if pending_sensors:
            counters["dropped_tail_sensors"] += 0  # Retained with edge-inferred flag if possible.
            self._emit_pending(pending_sensors, previous_gps, None, output, header=header, edge="end")

        if not output["field"]:
            raise MagneticReadError("No magnetic sensor events could be georeferenced from the EnMag acquisition log")

        timestamps = np.asarray(output["timestamp"], dtype="datetime64[ms]")
        field = np.asarray(output["field"], dtype=float)
        longitude = np.asarray(output["longitude"], dtype=float)
        latitude = np.asarray(output["latitude"], dtype=float)
        altitude = np.asarray(output["altitude"], dtype=float)
        movement = self._movement_summary(longitude, latitude, timestamps)
        classification = self._classify_acquisition(movement)
        source_crs = self._source_crs(options)
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
        # Prefer BNO heading for the generic heading channel where available.
        bno = channels["bno_heading_deg"]
        heading = channels["heading"].copy()
        bno_valid = np.isfinite(bno)
        heading[bno_valid] = bno[bno_valid]
        channels["heading"] = heading

        invalid_sensor = np.asarray(output["validation_bad"], dtype=bool)
        gps_fix = np.asarray(output["fix_quality"], dtype=float)
        quality_flags = {
            "sensor_validation_bad": invalid_sensor,
            "sensor_validation_valid": ~invalid_sensor,
            "gps_invalid_fix": gps_fix <= 0,
            "gps_pps_missing": np.asarray(output["pps_valid"], dtype=float) < 0.5,
            "georef_edge_inferred": np.asarray(output["georef_edge_inferred"], dtype=bool),
        }
        counters["exportable_sample_count"] = int(field.size)
        counters["invalid_sensor_ratio_pct"] = 100.0 * float(np.count_nonzero(invalid_sensor)) / max(field.size, 1)

        n = field.size
        if options.role == MagneticDataRole.BASE:
            line_id = np.full(n, "", dtype=object)
            line_type = np.full(n, MagneticLineType.BASE.value, dtype=object)
            survey_type = MagneticSurveyType.BASE_STATION
        else:
            if classification == "stationary":
                line_id = np.full(n, "", dtype=object)
                line_type = np.full(n, MagneticLineType.UNKNOWN.value, dtype=object)
            else:
                line_id = np.full(n, header.get("log_name") or header.get("name") or path.stem, dtype=object)
                line_type = np.full(n, MagneticLineType.TRAVERSE.value, dtype=object)
            survey_type = options.survey_type

        metadata = dict(options.metadata)
        metadata.update(
            {
                "reader": type(self).__name__,
                "format_id": "enmag_event_acquisition_log",
                "instrument_make": header.get("instrument_make", header.get("make", "EnMag/Enerson")),
                "instrument_model": header.get("instrument_model", header.get("model", "EnMag acquisition logger")),
                "log_name": header.get("log_name", path.stem),
                "timestamp_source": "GPS event-order interpolation",
                "georeferencing_method": "FIFO sensor events interpolated between adjacent GPS fixes",
                "sensor_validation_good_char": header.get("sensor_validation_good_char", "_"),
                "sensor_validation_bad_char": header.get("sensor_validation_bad_char", "*"),
                "source_coordinate_type": "latitude_longitude",
                "source_crs_detected": "EPSG:4326",
                "source_crs_assumption": "GPS latitude/longitude interpreted as WGS84",
                "recommended_working_crs": self._recommended_utm_crs_from_arrays(longitude, latitude),
                "acquisition_classification": classification,
                "movement_summary": movement,
                "source_header": header,
                "parse_report": counters,
                "source_sensor_records": counters["sensor_records"],
                "source_gps_records": counters["gps_records"],
                "invalid_sensor_records": counters["invalid_sensor_records"],
                "invalid_sensor_ratio_pct": counters["invalid_sensor_ratio_pct"],
                "imported_records": int(n),
                "column_mapping": {
                    "total_field": "! magnetic sensor event",
                    "timestamp": "GPS/inferred",
                    "x": "lon_deg",
                    "y": "lat_deg",
                    "elevation": "alt_m",
                    "heading": "BNO/GPS heading",
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
            magnetic_units=options.magnetic_units or "nT",
            quality_flags=quality_flags,
        )

    @staticmethod
    def _is_header_line(line: str) -> bool:
        if line.startswith(("#", "//", ";;")):
            return True
        text = line.lower()
        return ("=" in line and any(token in text for token in ("enmag", "sensor_", "gps_", "log_", "instrument", "logger")))

    @staticmethod
    def _consume_header_line(line: str, header: dict[str, str]) -> None:
        text = line.lstrip("#;/ ").strip()
        if "=" not in text:
            return
        key, value = text.split("=", 1)
        key = key.strip().lower().replace(" ", "_")
        if key:
            header[key] = value.strip()

    @classmethod
    def _parse_sensor(cls, line: str) -> EnmagSensorSample | None:
        match = _SENSOR_RE.match(line.strip())
        if not match:
            return None
        suffix = cls._parse_suffix(match.group("suffix"))
        validation = match.group("validation") or "_"
        return EnmagSensorSample(
            field_nt=float(match.group("field")),
            validation=validation,
            counter=cls._safe_int(match.group("counter")),
            sensitivity=cls._safe_float(match.group("sensitivity")),
            bno_heading_deg=cls._first_float(suffix, "bno", "bno_heading", "bno_heading_deg", "heading"),
            mx=cls._first_float(suffix, "mx", "bno_mx"),
            my=cls._first_float(suffix, "my", "bno_my"),
            mz=cls._first_float(suffix, "mz", "bno_mz"),
            raw_line=line,
        )

    @classmethod
    def _parse_gps(cls, line: str) -> EnmagGpsFix | None:
        text = line.strip()
        if text.upper().startswith("@GPS"):
            parts = [part.strip() for part in text.split(",")]
            try:
                # Common EnMag/Bulucu layout: @GPS,PPS=Y,iso,lat,lon,alt,hdop,sats,fix,heading
                start_index = 1
                pps_token = parts[1] if len(parts) > 1 else ""
                pps = pps_token.split("=", 1)[1].strip().upper() if "=" in pps_token else pps_token.upper()
                if len(parts) >= 10:
                    timestamp = cls._parse_time(parts[2])
                    return EnmagGpsFix(
                        timestamp=timestamp,
                        latitude_deg=float(parts[3]),
                        longitude_deg=float(parts[4]),
                        altitude_m=cls._safe_float(parts[5]),
                        hdop=cls._safe_float(parts[6]),
                        satellites=cls._safe_float(parts[7]),
                        fix_quality=cls._safe_float(parts[8], 1.0),
                        heading_deg=cls._safe_float(parts[9]),
                        pps_valid=pps in {"Y", "YES", "1", "TRUE"},
                        raw_line=line,
                    )
                # Key-value fallback: @GPS time=..., lat=..., lon=...
                suffix = cls._parse_suffix(text)
                timestamp = cls._parse_time(cls._first_value(suffix, "time", "timestamp", "gps_iso_utc", "iso"))
                return EnmagGpsFix(
                    timestamp=timestamp,
                    latitude_deg=cls._first_float(suffix, "lat", "latitude", "lat_deg"),
                    longitude_deg=cls._first_float(suffix, "lon", "lng", "longitude", "lon_deg"),
                    altitude_m=cls._first_float(suffix, "alt", "altitude", "alt_m", "elevation"),
                    hdop=cls._first_float(suffix, "hdop", default=float("nan")),
                    satellites=cls._first_float(suffix, "sat", "sats", "satellites", default=float("nan")),
                    fix_quality=cls._first_float(suffix, "fix", "quality", "fix_quality", default=1.0),
                    heading_deg=cls._first_float(suffix, "heading", "gps_heading", default=float("nan")),
                    pps_valid=str(cls._first_value(suffix, "pps", "pps_valid", default="Y")).upper() in {"Y", "YES", "1", "TRUE"},
                    raw_line=line,
                )
            except (ValueError, IndexError, KeyError):
                return None
        # NMEA fallback handles only time/lat/lon fields from GGA/RMC-like sentences.
        if text.startswith(("$GPGGA", "$GNGGA")):
            parts = text.split(",")
            try:
                return EnmagGpsFix(
                    timestamp=cls._nmea_time(parts[1]),
                    latitude_deg=cls._nmea_coordinate(parts[2], parts[3]),
                    longitude_deg=cls._nmea_coordinate(parts[4], parts[5]),
                    altitude_m=cls._safe_float(parts[9]),
                    hdop=cls._safe_float(parts[8]),
                    satellites=cls._safe_float(parts[7]),
                    fix_quality=cls._safe_float(parts[6]),
                    heading_deg=float("nan"),
                    pps_valid=True,
                    raw_line=line,
                )
            except (ValueError, IndexError):
                return None
        return None

    @classmethod
    def _emit_pending(
        cls,
        pending: list[EnmagSensorSample],
        previous_gps: EnmagGpsFix | None,
        current_gps: EnmagGpsFix | None,
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
            start_time = cls._parse_iso(header.get("start_iso") or header.get("start_time")) or (current_gps.timestamp - timedelta(seconds=interval_s))
            start = EnmagGpsFix(start_time, current_gps.latitude_deg, current_gps.longitude_deg, current_gps.altitude_m, current_gps.hdop, current_gps.satellites, current_gps.fix_quality, current_gps.heading_deg, current_gps.pps_valid, current_gps.raw_line)
            end = current_gps
            fractions = [(index + 0.5) / max(len(pending), 1) for index in range(len(pending))]
            inferred_edge = True
        elif previous_gps is not None:
            stop_time = cls._parse_iso(header.get("stop_iso") or header.get("stop_time"))
            if stop_time is None or stop_time <= previous_gps.timestamp:
                stop_time = previous_gps.timestamp + timedelta(seconds=interval_s * len(pending))
            start = previous_gps
            end = EnmagGpsFix(stop_time, previous_gps.latitude_deg, previous_gps.longitude_deg, previous_gps.altitude_m, previous_gps.hdop, previous_gps.satellites, previous_gps.fix_quality, previous_gps.heading_deg, previous_gps.pps_valid, previous_gps.raw_line)
            fractions = [(index + 0.5) / max(len(pending), 1) for index in range(len(pending))]
            inferred_edge = True
        else:
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
            output["validation_marker"].append(sample.validation)
            output["sensor_counter"].append(sample.counter if sample.counter is not None else float("nan"))
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
            output["raw_line"].append(sample.raw_line)

    def _scan(self, path: Path, *, preview_limit: int, encoding: str) -> tuple[dict[str, str], dict[str, int], list[dict[str, Any]], dict[str, Any]]:
        header: dict[str, str] = {}
        counters = {"total_records": 0, "gps_records": 0, "gps_points": 0, "sensor_records": 0, "invalid_sensor_records": 0, "malformed_sensor_records": 0, "malformed_gps_records": 0, "inline_event_records": 0, "inline_bad_data_events": 0}
        preview: list[dict[str, Any]] = []
        lons: list[float] = []
        lats: list[float] = []
        times: list[np.datetime64] = []
        with path.open("r", encoding=encoding, errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                counters["total_records"] += 1
                if self._is_header_line(line):
                    self._consume_header_line(line, header)
                    continue
                if line.startswith("!"):
                    counters["sensor_records"] += 1
                    sample = self._parse_sensor(line)
                    if sample is None:
                        counters["malformed_sensor_records"] += 1
                    elif sample.validation == "*":
                        counters["invalid_sensor_records"] += 1
                    continue
                if line.upper().startswith("@GPS") or line.startswith("$GP") or line.startswith("$GN"):
                    counters["gps_records"] += 1
                    gps = self._parse_gps(line)
                    if gps is None:
                        counters["malformed_gps_records"] += 1
                        continue
                    counters["gps_points"] += 1
                    lons.append(gps.longitude_deg)
                    lats.append(gps.latitude_deg)
                    times.append(np.datetime64(gps.timestamp.replace(tzinfo=None), "ms"))
                    if len(preview) < preview_limit:
                        preview.append({"timestamp": gps.timestamp.isoformat(), "latitude_deg": gps.latitude_deg, "longitude_deg": gps.longitude_deg, "altitude_m": gps.altitude_m, "hdop": gps.hdop, "satellites": gps.satellites, "fix_quality": gps.fix_quality})
                    continue
                counters["inline_event_records"] += 1
                if any(token in line.lower() for token in ("bad", "error", "invalid", "reject", "noise")):
                    counters["inline_bad_data_events"] += 1
        movement = self._movement_summary(np.asarray(lons, dtype=float), np.asarray(lats, dtype=float), np.asarray(times, dtype="datetime64[ms]"))
        if preview:
            movement["representative_fix"] = preview[len(preview) // 2]
        counters["invalid_sensor_ratio_pct"] = 100.0 * counters["invalid_sensor_records"] / max(counters["sensor_records"], 1)
        counters["exportable_sample_count"] = max(0, counters["sensor_records"] - counters["malformed_sensor_records"])
        return header, counters, preview, movement

    @staticmethod
    def _parse_suffix(text: str | None) -> dict[str, str]:
        if not text:
            return {}
        suffix: dict[str, str] = {}
        cleaned = text.lstrip(",; ")
        for match in _KEY_VALUE_RE.finditer(cleaned):
            suffix[match.group("key").strip().lower().replace(" ", "_")] = match.group("value").strip()
        # Also handle comma CSV tokens without key-value names from some exports.
        for token in re.split(r"[,;]", cleaned):
            if "=" in token or ":" in token:
                continue
            token = token.strip()
            if not token:
                continue
        return suffix

    @staticmethod
    def _first_value(mapping: dict[str, str], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in mapping:
                return mapping[key]
        return default

    @classmethod
    def _first_float(cls, mapping: dict[str, str], *keys: str, default: float = float("nan")) -> float:
        return cls._safe_float(cls._first_value(mapping, *keys, default=default), default)

    @staticmethod
    def _safe_float(value: Any, default: float = float("nan")) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if value is None:
            raise ValueError("missing time")
        text = str(value).strip()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return EnmagAcquisitionReader._parse_time(value)
        except ValueError:
            return None

    @staticmethod
    def _nmea_time(value: str) -> datetime:
        now = datetime.now(timezone.utc)
        text = value.strip()
        if len(text) < 6:
            raise ValueError("invalid NMEA time")
        hour = int(text[0:2])
        minute = int(text[2:4])
        second = float(text[4:])
        whole = int(second)
        micro = int(round((second - whole) * 1_000_000))
        return now.replace(hour=hour, minute=minute, second=whole, microsecond=micro)

    @staticmethod
    def _nmea_coordinate(value: str, hemisphere: str) -> float:
        raw = float(value)
        degrees = int(raw // 100)
        minutes = raw - degrees * 100
        result = degrees + minutes / 60.0
        return -result if hemisphere.upper() in {"S", "W"} else result

    @staticmethod
    def _source_crs(options: ReaderOptions) -> str:
        if not options.crs:
            return "EPSG:4326"
        normalised = str(options.crs).strip().upper().replace(" ", "")
        if normalised in {"4326", "EPSG:4326", "WGS84", "WGS-84"}:
            return "EPSG:4326"
        raise MagneticSchemaError("EnMag event logs store GPS latitude/longitude coordinates. Source CRS is WGS84/EPSG:4326.")

    @staticmethod
    def _recommended_utm_crs(preview_or_fix: Any) -> str | None:
        if not preview_or_fix:
            return None
        try:
            lon = float(preview_or_fix.get("longitude_deg"))
            lat = float(preview_or_fix.get("latitude_deg"))
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
        return cls._recommended_utm_crs({"longitude_deg": float(np.nanmedian(longitude[valid])), "latitude_deg": float(np.nanmedian(latitude[valid]))})

    @staticmethod
    def _movement_summary(longitude: np.ndarray, latitude: np.ndarray, timestamps: np.ndarray) -> dict[str, Any]:
        valid = np.isfinite(longitude) & np.isfinite(latitude)
        if np.count_nonzero(valid) < 2:
            return {"valid_gps_records": int(np.count_nonzero(valid)), "bounding_diagonal_m": 0.0, "net_displacement_m": 0.0, "track_length_m": 0.0, "median_step_m": 0.0, "p95_step_m": 0.0, "duration_s": 0.0}
        lon = longitude[valid]
        lat = latitude[valid]
        radius = 6_371_008.8
        lon0 = np.radians(float(np.nanmedian(lon)))
        lat0 = np.radians(float(np.nanmedian(lat)))
        x = radius * (np.radians(lon) - lon0) * np.cos(lat0)
        y = radius * (np.radians(lat) - lat0)
        steps = np.hypot(np.diff(x), np.diff(y))
        valid_times = timestamps[~np.isnat(timestamps)] if timestamps.size else np.empty(0, dtype="datetime64[ms]")
        duration_s = float((valid_times.max() - valid_times.min()) / np.timedelta64(1, "s")) if valid_times.size >= 2 else 0.0
        return {"valid_gps_records": int(lon.size), "bounding_diagonal_m": float(np.hypot(np.nanmax(x) - np.nanmin(x), np.nanmax(y) - np.nanmin(y))), "net_displacement_m": float(np.hypot(x[-1] - x[0], y[-1] - y[0])), "track_length_m": float(np.nansum(steps)), "median_step_m": float(np.nanmedian(steps)) if steps.size else 0.0, "p95_step_m": float(np.nanpercentile(steps, 95)) if steps.size else 0.0, "duration_s": duration_s}

    @staticmethod
    def _classify_acquisition(movement: dict[str, Any]) -> str:
        duration = float(movement.get("duration_s", 0.0) or 0.0)
        bounding = float(movement.get("bounding_diagonal_m", 0.0) or 0.0)
        net = float(movement.get("net_displacement_m", 0.0) or 0.0)
        median_step = float(movement.get("median_step_m", 0.0) or 0.0)
        if duration >= 300.0 and bounding <= 150.0 and net <= 100.0 and median_step <= 0.75:
            return "stationary"
        return "moving"

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
            return EnmagAcquisitionReader._lerp(a, b, fraction)
        delta = ((b - a + 180.0) % 360.0) - 180.0
        return float((a + delta * fraction) % 360.0)
