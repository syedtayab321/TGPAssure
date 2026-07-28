from __future__ import annotations

import csv
import re
from itertools import chain
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from modules.magnetic.constants import BASE_TOTAL_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.exceptions import MagneticReadError, MagneticSchemaError
from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticLineType, MagneticSurveyType
from modules.magnetic.readers.base_reader import MagneticFormatReader, ReaderOptions
from modules.magnetic.readers.column_mapper import MagneticColumnMapper, normalise_header
from modules.magnetic.readers.schema_detector import MagneticSchemaDetector


class GenericDelimitedMagneticReader(MagneticFormatReader):
    EXTENSIONS = {".csv", ".txt", ".dat", ".log", ".xyz"}

    def can_read(self, path: Path) -> bool:
        return path.suffix.lower() in self.EXTENSIONS and path.is_file()

    def inspect(self, path: Path, options: ReaderOptions | None = None) -> dict[str, Any]:
        options = options or ReaderOptions()
        delimiter, headers, preview = self._inspect_file(path, options)
        inspection = MagneticSchemaDetector().inspect(headers, base=options.role == MagneticDataRole.BASE)
        detected_crs, coordinate_type = self._infer_crs_from_headers(headers, inspection.mapping, options.crs)
        return {
            "path": str(path),
            "reader": type(self).__name__,
            "format": "Delimited magnetic table",
            "format_id": "generic_delimited",
            "delimiter": delimiter,
            "headers": headers,
            "preview": preview,
            "mapping": inspection.mapping,
            "required_missing": inspection.required_missing,
            "confidence": inspection.confidence,
            "detected_crs": detected_crs,
            "coordinate_type": coordinate_type,
            "crs_confidence": "medium" if detected_crs else "unknown",
            "recommended_working_crs": None,
        }

    def read(self, path: Path, options: ReaderOptions | None = None) -> MagneticDataset:
        options = options or ReaderOptions()
        delimiter, headers, _ = self._inspect_file(path, options)
        detected = MagneticColumnMapper().detect(headers)
        mapping = MagneticColumnMapper().merge(detected, options.column_mapping)
        if "total_field" not in mapping:
            raise MagneticSchemaError(
                "A total magnetic field column could not be identified. "
                "For ordinary tabular files, include a column such as mag, mag_nt, "
                "total_field, tmi or total_intensity, or provide a column mapping."
            )
        if "timestamp" not in mapping and not ({"date", "time"} <= mapping.keys()):
            raise MagneticSchemaError("A timestamp column, or separate date and time columns, is required")

        columns: dict[str, list[Any]] = {key: [] for key in mapping}
        rejected_rows = 0
        with path.open("r", encoding=options.encoding, errors="replace", newline="") as stream:
            rows = self._dict_rows(self._data_lines(stream), delimiter)
            for row in rows:
                if not row or all(not str(value or "").strip() for value in row.values()):
                    continue
                try:
                    for canonical, source in mapping.items():
                        columns[canonical].append(row.get(source, ""))
                except Exception:
                    rejected_rows += 1
                    continue

        if not columns["total_field"]:
            raise MagneticReadError("Magnetic input contains no data records")

        timestamps = np.array(
            [self._parse_timestamp(columns, index) for index in range(len(columns["total_field"]))],
            dtype="datetime64[ms]",
        )
        total_field = self._float_array(columns["total_field"])
        role = options.role
        channels = {BASE_TOTAL_FIELD if role == MagneticDataRole.BASE else RAW_TOTAL_FIELD: total_field}
        if "base_field" in columns:
            channels[BASE_TOTAL_FIELD] = self._float_array(columns["base_field"])
        if "sensor_1" in columns:
            channels["sensor_1_raw"] = self._float_array(columns["sensor_1"])
        if "sensor_2" in columns:
            channels["sensor_2_raw"] = self._float_array(columns["sensor_2"])
        for source_name in (
            "temperature", "gps_quality", "gps_hdop", "gps_pps_valid", "satellites", "heading", "speed",
            "terrain_clearance", "roll", "pitch", "yaw",
        ):
            if source_name in columns:
                channels[source_name] = self._float_array(columns[source_name])

        x = self._float_array(columns.get("x", []), length=total_field.size)
        y = self._float_array(columns.get("y", []), length=total_field.size)
        elevation = self._float_array(columns.get("elevation", []), length=total_field.size)
        line_id = self._string_array(columns.get("line_id", []), total_field.size)
        station_id = self._string_array(columns.get("station_id", []), total_field.size)
        line_type = self._line_type_array(columns.get("line_type", []), total_field.size, role)

        detected_crs, coordinate_type = self._infer_crs_from_headers(headers, mapping, options.crs)
        if not detected_crs:
            detected_crs, coordinate_type = self._infer_crs_from_values(x, y, options.crs)
        coordinate_units = "degrees" if detected_crs and "4326" in detected_crs else options.coordinate_units

        metadata = dict(options.metadata)
        metadata.update(
            {
                "reader": type(self).__name__,
                "format_id": "generic_delimited",
                "delimiter": delimiter,
                "column_mapping": mapping,
                "rejected_rows": rejected_rows,
                "source_headers": headers,
                "source_coordinate_type": coordinate_type,
                "source_crs_detected": detected_crs,
            }
        )
        return MagneticDataset(
            source_path=path,
            role=role,
            survey_type=MagneticSurveyType.BASE_STATION if role == MagneticDataRole.BASE else options.survey_type,
            timestamps=timestamps,
            channels=channels,
            x=x,
            y=y,
            elevation=elevation,
            line_id=line_id,
            station_id=station_id,
            line_type=line_type,
            metadata=metadata,
            crs=detected_crs,
            coordinate_units=coordinate_units,
            magnetic_units=options.magnetic_units,
        )

    def _inspect_file(self, path: Path, options: ReaderOptions) -> tuple[str, list[str], list[dict[str, str]]]:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size == 0:
            raise MagneticReadError("Magnetic source file is empty")
        with path.open("r", encoding=options.encoding, errors="replace", newline="") as stream:
            lines = []
            for line in stream:
                stripped = line.strip()
                if stripped and not stripped.startswith(("#", "//", ";;")):
                    lines.append(line)
                if len(lines) >= 25:
                    break
        if not lines:
            raise MagneticReadError("No data header could be found")
        sample = "".join(lines)
        delimiter = options.delimiter or self._detect_delimiter(sample)
        rows = list(self._dict_rows(lines, delimiter))
        if delimiter == " ":
            headers = re.split(r"\s+", lines[0].strip())
        else:
            headers = [str(name).strip() for name in next(csv.reader([lines[0]], delimiter=delimiter), [])]
        preview = rows[:5]
        if len(headers) <= 1:
            raise MagneticSchemaError(
                "Could not identify a delimited header row. If this is an instrument-native log, "
                "use a supported native reader rather than treating it as a CSV table."
            )
        return delimiter, headers, preview

    @staticmethod
    def _dict_rows(lines: Iterable[str], delimiter: str) -> Iterable[dict[str, str]]:
        """Yield rows while treating arbitrary whitespace as one delimiter.

        Field/base magnetometer exports frequently use aligned columns separated
        by a variable number of spaces. ``csv.DictReader(delimiter=" ")`` creates
        empty pseudo-columns for those files, so whitespace tables need explicit
        tokenization while comma/tab/semicolon files retain CSV semantics.
        """
        iterator = iter(lines)
        try:
            header_line = next(iterator)
        except StopIteration:
            return
        if delimiter != " ":
            reader = csv.DictReader(chain([header_line], iterator), delimiter=delimiter)
            yield from reader
            return
        headers = re.split(r"\s+", header_line.strip())
        for line in iterator:
            values = re.split(r"\s+", line.strip())
            if not values:
                continue
            # Preserve a final free-text field rather than shifting all columns.
            if len(values) > len(headers) and headers:
                values = values[: len(headers) - 1] + [" ".join(values[len(headers) - 1 :])]
            if len(values) < len(headers):
                values += [""] * (len(headers) - len(values))
            yield dict(zip(headers, values))

    @staticmethod
    def _detect_delimiter(sample: str) -> str:
        try:
            return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            first = sample.splitlines()[0]
            counts = {delimiter: first.count(delimiter) for delimiter in (",", "\t", ";", "|")}
            delimiter = max(counts, key=counts.get)
            if counts[delimiter] == 0:
                return " "
            return delimiter

    @staticmethod
    def _data_lines(stream: Iterable[str]) -> Iterable[str]:
        for line in stream:
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "//", ";;")):
                yield line

    @staticmethod
    def _float_array(values: list[Any], length: int | None = None) -> np.ndarray:
        if not values:
            return np.full(length or 0, np.nan, dtype=float)
        parsed: list[float] = []
        for value in values:
            text = str(value or "").strip().replace(" ", "")
            if text.count(",") == 1 and "." not in text:
                text = text.replace(",", ".")
            try:
                parsed.append(float(text))
            except (TypeError, ValueError):
                parsed.append(float("nan"))
        return np.asarray(parsed, dtype=float)

    @staticmethod
    def _string_array(values: list[Any], length: int) -> np.ndarray:
        if not values:
            return np.full(length, "", dtype=object)
        return np.asarray([str(value or "").strip() for value in values], dtype=object)

    @staticmethod
    def _line_type_array(values: list[Any], length: int, role: MagneticDataRole) -> np.ndarray:
        if role == MagneticDataRole.BASE:
            return np.full(length, MagneticLineType.BASE.value, dtype=object)
        if not values:
            return np.full(length, MagneticLineType.UNKNOWN.value, dtype=object)
        result = []
        for value in values:
            text = str(value or "").strip().lower()
            if text.startswith("t") and "tie" in text:
                result.append(MagneticLineType.TIE.value)
            elif text in {"tie", "control"}:
                result.append(text)
            elif text in {"repeat", "rep"}:
                result.append(MagneticLineType.REPEAT.value)
            else:
                result.append(MagneticLineType.TRAVERSE.value if text else MagneticLineType.UNKNOWN.value)
        return np.asarray(result, dtype=object)

    @staticmethod
    def _parse_timestamp(columns: dict[str, list[Any]], index: int) -> np.datetime64:
        if "timestamp" in columns:
            text = str(columns["timestamp"][index] or "").strip()
        else:
            text = f"{columns['date'][index]} {columns['time'][index]}".strip()
        if not text:
            return np.datetime64("NaT", "ms")
        text = text.replace("Z", "+00:00")
        formats = (
            None,
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S.%f",
            "%d/%m/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
            "%Y%m%d %H%M%S.%f",
            "%Y%m%d %H%M%S",
        )
        for format_string in formats:
            try:
                parsed = datetime.fromisoformat(text) if format_string is None else datetime.strptime(text, format_string)
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return np.datetime64(parsed, "ms")
            except ValueError:
                continue
        return np.datetime64("NaT", "ms")

    @staticmethod
    def _infer_crs_from_headers(
        headers: list[str], mapping: dict[str, str], explicit_crs: str | None,
    ) -> tuple[str | None, str]:
        if explicit_crs:
            return explicit_crs.strip(), "explicit"
        x_name = normalise_header(mapping.get("x", ""))
        y_name = normalise_header(mapping.get("y", ""))
        longitude_tokens = ("lon", "long", "longitude", "gps_longitude")
        latitude_tokens = ("lat", "latitude", "gps_latitude")
        x_is_lon = any(token == x_name or token in x_name for token in longitude_tokens)
        y_is_lat = any(token == y_name or token in y_name for token in latitude_tokens)
        if x_is_lon and y_is_lat:
            return "EPSG:4326", "latitude_longitude"
        return None, "projected_or_unknown"

    @staticmethod
    def _infer_crs_from_values(x: np.ndarray, y: np.ndarray, explicit_crs: str | None) -> tuple[str | None, str]:
        if explicit_crs:
            return explicit_crs.strip(), "explicit"
        valid = np.isfinite(x) & np.isfinite(y)
        if np.any(valid):
            xv = x[valid]
            yv = y[valid]
            if np.all((xv >= -180.0) & (xv <= 180.0)) and np.all((yv >= -90.0) & (yv <= 90.0)):
                return "EPSG:4326", "latitude_longitude_inferred"
        return None, "projected_or_unknown"
