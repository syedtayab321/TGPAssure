from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Iterable

from modules.geodetic.models import (
    DcRecord,
    FIELD_LABELS,
    GeodeticDataset,
    RECORD_SCHEMAS,
    SCHEMA_BY_RECORD_ID,
)


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_RECORD_RE = re.compile(r"^\s*([0-9A-Fa-f]{2})(?=\s|,|;|\t|\||$)")
_KEY_VALUE_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9 _/#().-]{1,50})\s*[:=]\s*(?P<value>[^,;\t|]+)"
)
_DMS_RE = re.compile(
    r"^\s*(?P<deg>[+-]?\d+(?:\.\d+)?)\D+"
    r"(?P<min>\d+(?:\.\d+)?)?\D*"
    r"(?P<sec>\d+(?:\.\d+)?)?\D*"
    r"(?P<hem>[NSEW])?\s*$",
    re.IGNORECASE,
)


def _norm(value: str) -> str:
    return _NORMALIZE_RE.sub("", str(value).strip().lower())


def _alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for schema in RECORD_SCHEMAS:
        for key, label in schema.fields:
            for alias in {key, label, label.replace("#", "number"), key.replace("_", " ")}:
                aliases[_norm(alias)] = key
    extras = {
        "minsats": "min_satellites", "minsatellites": "min_satellites", "satellites": "min_satellites",
        "nsats": "min_satellites", "numberofsatellites": "min_satellites",
        "reldop": "relative_dops", "relativedop": "relative_dops", "relativedops": "relative_dops",
        "pdop": "pdop", "hdop": "hdop", "vdop": "vdop", "gdop": "relative_dops",
        "rms": "rms_m", "positionrms": "rms_m", "horizontalrms": "horizontal_sd_m",
        "horizontalsd": "horizontal_sd_m", "verticalsd": "vertical_sd_m",
        "latitude": "latitude_deg", "lat": "latitude_deg", "longitude": "longitude_deg", "lon": "longitude_deg",
        "lng": "longitude_deg", "easting": "local_easting_m", "east": "local_easting_m", "x": "local_easting_m",
        "xcoordinate": "local_easting_m", "localeasting": "local_easting_m", "grid_easting": "local_easting_m",
        "northing": "local_northing_m", "north": "local_northing_m", "y": "local_northing_m",
        "ycoordinate": "local_northing_m", "localnorthing": "local_northing_m", "grid_northing": "local_northing_m",
        "ellipsoidheight": "ellipsoid_height_m", "height": "ellipsoid_height_m", "elevation": "ellipsoid_height_m",
        "point": "point_name", "pointname": "point_name", "station": "point_name",
        "gpsweek": "start_gps_week", "gpstime": "start_gps_time_s", "deltatime": "delta_time_s",
        "horizontalprecision": "horizontal_precision_m", "verticalprecision": "vertical_precision_m",
        "receiver": "receiver_type", "receiversn": "receiver_serial_number",
    }
    aliases.update({_norm(key): value for key, value in extras.items()})
    return aliases


ALIASES = _alias_map()


def _coerce(value: str, key: str = "") -> Any:
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return ""
    if key in {"latitude_deg", "longitude_deg", "project_latitude_deg", "project_longitude_deg"}:
        parsed = _parse_coordinate(text)
        if parsed is not None:
            return parsed
    normalized = text.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text) else text
    try:
        if re.fullmatch(r"[+-]?\d+", normalized):
            return int(normalized)
        if re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", normalized):
            return float(normalized)
    except ValueError:
        pass
    return text


def _parse_coordinate(text: str) -> float | None:
    stripped = text.strip()
    try:
        numeric = float(stripped)
        return numeric
    except ValueError:
        pass
    match = _DMS_RE.match(stripped.replace("°", " ").replace("'", " ").replace('"', " "))
    if not match:
        return None
    try:
        degrees = float(match.group("deg"))
        minutes = float(match.group("min") or 0.0)
        seconds = float(match.group("sec") or 0.0)
    except ValueError:
        return None
    sign = -1.0 if degrees < 0 else 1.0
    hemisphere = (match.group("hem") or "").upper()
    if hemisphere in {"S", "W"}:
        sign = -1.0
    elif hemisphere in {"N", "E"}:
        sign = 1.0
    return sign * (abs(degrees) + minutes / 60.0 + seconds / 3600.0)


class DcFileReader:
    """Best-effort, traceable reader for text-exported survey/DC records.

    Trimble/legacy DC formats are versioned vendor exchange formats.  This reader
    intentionally avoids inventing undocumented fixed byte offsets.  It supports
    explicit record identifiers, key/value exports, common delimited exports and
    CSV tables while preserving every original line for audit/review.
    """

    SUPPORTED_EXTENSIONS = {".dc", ".dcf", ".txt", ".csv", ".tsv", ".dat"}

    def inspect(self, path: str | Path) -> dict[str, Any]:
        source = Path(path).expanduser().resolve()
        text, encoding = self._read_text(source)
        lines = text.splitlines()
        ids = []
        for line in lines[:5000]:
            match = _RECORD_RE.match(line)
            if match and match.group(1).upper() in SCHEMA_BY_RECORD_ID:
                ids.append(match.group(1).upper())
        return {
            "path": str(source), "encoding": encoding, "line_count": len(lines),
            "recognized_record_ids": sorted(set(ids)), "recognized_record_count": len(ids),
            "is_candidate": bool(ids) or self._looks_like_tabular(text),
        }

    def read(self, path: str | Path) -> GeodeticDataset:
        source = Path(path).expanduser().resolve()
        text, encoding = self._read_text(source)
        records = self._parse_record_lines(text)
        source_format = "dc-record-text"
        if not records:
            records = self._parse_tabular(text)
            source_format = "delimited-table"
        if not records:
            raise ValueError(
                "No recognized geodetic/DC records were found. The reader supports DC record-text or "
                "delimited survey exports containing GNSS/QC fields. Original vendor binary/proprietary formats "
                "must first be exported to a documented text/DC exchange format."
            )
        recognized_values = sum(len(record.values) for record in records)
        return GeodeticDataset(
            source_path=source,
            records=records,
            source_format=source_format,
            metadata={
                "encoding": encoding,
                "recognized_value_count": recognized_values,
                "parser_note": (
                    "Semantic DC/text parsing; raw source lines are preserved. No undocumented fixed vendor offsets are assumed."
                ),
            },
        )

    @staticmethod
    def _read_text(path: Path) -> tuple[str, str]:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(path)
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            raise ValueError("The selected file appears binary. Export it to a supported DC/text exchange format first.")
        for encoding in ("utf-8-sig", "cp1252", "latin1"):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        return data.decode("latin1", errors="replace"), "latin1-replace"

    @staticmethod
    def _looks_like_tabular(text: str) -> bool:
        first = next((line for line in text.splitlines() if line.strip()), "")
        normalized = _norm(first)
        return any(token in normalized for token in ("pdop", "hdop", "latitude", "longitude", "satellite", "rms"))

    def _parse_record_lines(self, text: str) -> list[DcRecord]:
        records: list[DcRecord] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not raw_line.strip() or raw_line.lstrip().startswith(("#", "//")):
                continue
            match = _RECORD_RE.match(raw_line)
            if not match:
                continue
            record_id = match.group(1).upper()
            schema = SCHEMA_BY_RECORD_ID.get(record_id)
            if schema is None:
                continue
            payload = raw_line[match.end():].strip().lstrip(",;|\t ")
            values = self._parse_payload(payload, schema.fields)
            records.append(DcRecord(record_id=record_id, values=values, raw_line=raw_line, line_number=line_number))
        return records

    def _parse_payload(self, payload: str, fields: Iterable[tuple[str, str]]) -> dict[str, Any]:
        field_list = list(fields)
        if not payload:
            return {}
        key_values: dict[str, Any] = {}
        for match in _KEY_VALUE_RE.finditer(payload):
            key = ALIASES.get(_norm(match.group("key")))
            if key:
                key_values[key] = _coerce(match.group("value"), key)
        if key_values:
            return key_values

        # Prefer explicit separators. Whitespace-only sequential mapping is used
        # only as a transparent best-effort fallback for simple text exports.
        delimiter = None
        for candidate in ("\t", ",", ";", "|"):
            if candidate in payload:
                delimiter = candidate
                break
        if delimiter is not None:
            try:
                tokens = next(csv.reader([payload], delimiter=delimiter, skipinitialspace=True))
            except csv.Error:
                tokens = payload.split(delimiter)
        else:
            tokens = re.split(r"\s{2,}", payload.strip())
            if len(tokens) == 1:
                tokens = payload.split()
        values: dict[str, Any] = {}
        for (key, _label), token in zip(field_list, tokens):
            values[key] = _coerce(token, key)
        return values

    def _parse_tabular(self, text: str) -> list[DcRecord]:
        sample = "\n".join(text.splitlines()[:30])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
            if "\t" in sample:
                dialect.delimiter = "\t"
        try:
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        except Exception:
            return []
        if not reader.fieldnames:
            return []
        mapped = {header: ALIASES.get(_norm(header)) for header in reader.fieldnames}
        if not any(mapped.values()):
            return []
        records: list[DcRecord] = []
        for row_index, row in enumerate(reader, start=2):
            values = {
                key: _coerce(row.get(header, ""), key)
                for header, key in mapped.items() if key and str(row.get(header, "")).strip()
            }
            if not values:
                continue
            geographic_position_keys = {"latitude_deg", "longitude_deg", "ellipsoid_height_m", "point_name", "horizontal_precision_m", "vertical_precision_m", "measurement_method", "point_classification"}
            local_position_keys = {"local_easting_m", "local_northing_m", "local_ellipsoid_height_m", "point_name", "horizontal_precision_m", "vertical_precision_m", "measurement_method", "point_classification"}
            qc_keys = {"min_satellites", "relative_dops", "pdop", "hdop", "vdop", "rms_m", "positions_used", "horizontal_sd_m", "vertical_sd_m", "start_gps_week", "start_gps_time_s", "end_gps_week", "end_gps_time_s", "delta_time_s"}
            if {"latitude_deg", "longitude_deg"}.intersection(values):
                p_values = {key: value for key, value in values.items() if key in geographic_position_keys or key in {"local_easting_m", "local_northing_m"}}
                records.append(DcRecord("66", p_values, raw_line=str(row), line_number=row_index))
            elif {"local_easting_m", "local_northing_m"}.intersection(values):
                p_values = {key: value for key, value in values.items() if key in local_position_keys}
                if "local_ellipsoid_height_m" not in p_values and "ellipsoid_height_m" in values:
                    p_values["local_ellipsoid_height_m"] = values["ellipsoid_height_m"]
                records.append(DcRecord("68", p_values, raw_line=str(row), line_number=row_index))
            if qc_keys.intersection(values):
                q_values = {key: value for key, value in values.items() if key in qc_keys}
                records.append(DcRecord("C6", q_values, raw_line=str(row), line_number=row_index))
        return records
