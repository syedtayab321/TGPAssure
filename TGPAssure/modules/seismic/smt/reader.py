from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from .models import ImportOptions, SmtTestRecord


ALIASES: dict[str, tuple[str, ...]] = {
    "string_no": ("string", "string_no", "string_number", "string_id", "receiver", "station", "unit", "geophone", "sensor"),
    "serial": ("serial", "serial_no", "serial_number", "sn", "sensor_serial", "geophone_sn"),
    "tester": ("tester", "tester_no", "tester_id", "smt", "smt_no", "instrument", "unit_tester"),
    "operator": ("operator", "user", "tested_by", "technician", "crew_member"),
    "tested_at": ("datetime", "date_time", "test_time", "test_date", "tested_at", "timestamp", "date"),
    "test_date": ("test_date", "date", "tested_date"),
    "test_clock": ("test_clock", "clock", "time", "tested_time"),
    "model": ("model", "smt_model", "tester_model", "instrument_model", "device"),
    "source_result": ("result", "status", "test_result", "pass_fail", "outcome"),
    "noise": ("noise", "noise_mv", "noise_uv", "rms_noise", "nois"),
    "resistance": ("resistance", "res", "ohm", "ohms", "coil_resistance", "coil_res"),
    "frequency": ("frequency", "freq", "natural_frequency", "natural_freq", "fn", "hz"),
    "damping": ("damping", "damp", "damping_ratio"),
    "sensitivity": ("sensitivity", "sens", "mv_per_ms", "v_m_s", "output"),
    "temperature": ("temperature", "temp", "temperature_c", "degrees_c", "deg_c"),
    "distortion": ("distortion", "dist", "thd", "harmonic", "harmonic_distortion"),
    "impedance": ("impedance", "imp", "z", "imp_ohm", "impedance_ohm"),
    "polarity": ("polarity", "polar", "phase", "reverse", "reversed"),
    "notes": ("note", "notes", "remark", "remarks", "comment", "comments", "message"),
}

_SUPPORTED_TEXT_SUFFIXES = {".csv", ".txt", ".tsv", ".dat", ".asc", ".smt", ".log", ".out"}


def normalize_header(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-", "--"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] == b"MZ":
        raise ValueError(f"{path.name} is an executable, not an SMT result export.")
    if b"\x00" in data[:4096] and path.suffix.lower() != ".txt":
        raise ValueError(
            f"{path.name} appears to be a proprietary binary SMT file. "
            "The supplied reference PDF does not document that binary layout; export the tester results as CSV/TXT/ASCII first."
        )
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


class SmtResultReader:
    """Flexible SMT200/300/400 and SGT-II text-export reader.

    The source PDF describes database behavior and supported tester families but
    does not publish proprietary binary file layouts. This reader therefore
    supports common CSV, TSV, semicolon, pipe, fixed-width, whitespace and
    key/value ASCII exports while rejecting undocumented binary dumps clearly.
    """

    def read_files(self, paths: Iterable[str | Path], options: ImportOptions) -> tuple[list[SmtTestRecord], list[str]]:
        records: list[SmtTestRecord] = []
        warnings: list[str] = []
        for item in paths:
            path = Path(item)
            file_records, file_warnings = self.read(path, options)
            records.extend(file_records)
            warnings.extend(file_warnings)
        return records, warnings

    def read(self, path: str | Path, options: ImportOptions) -> tuple[list[SmtTestRecord], list[str]]:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.suffix.lower() not in _SUPPORTED_TEXT_SUFFIXES:
            # Still try text because many field exports have custom extensions.
            pass
        text = read_text(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        rows = self._read_table(source, text)
        if not rows:
            rows = self._read_key_value_blocks(source, text)
        if not rows:
            raise ValueError(
                f"No SMT result rows were recognized in {source.name}. Expected a table containing a string/serial and one or more test measurements."
            )
        output: list[SmtTestRecord] = []
        warnings: list[str] = []
        file_date = datetime.fromtimestamp(source.stat().st_mtime).date()
        for source_row, raw in rows:
            record = self._record_from_mapping(raw)
            record.source_file = source.name
            record.source_hash = digest
            record.source_row = int(source_row)
            record.raw = dict(raw)
            parsed, warning = self._resolve_date(record.original_tested_at, file_date, options)
            if warning:
                warnings.append(f"{source.name}:{source_row}: {warning}")
            if parsed is None and options.bad_date_mode == "reject":
                continue
            record.tested_at = parsed
            record.date_corrected = bool(warning and parsed is not None and options.bad_date_mode == "correct")
            if not record.model:
                record.model = self._infer_model(text)
            output.append(record)
        if not output:
            raise ValueError(f"All rows in {source.name} were rejected by the date/import rules.")
        return output, warnings

    def _read_table(self, path: Path, text: str) -> list[tuple[int, dict[str, str]]]:
        lines = [(i, line) for i, line in enumerate(text.splitlines(), start=1) if line.strip()]
        if len(lines) < 2:
            return []
        sample = "\n".join(line for _, line in lines[:30])
        delimiter: str | None = None
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            pass
        if delimiter is not None:
            parsed = [(line_no, next(csv.reader([line], delimiter=delimiter))) for line_no, line in lines]
        else:
            parsed = []
            for line_no, line in lines:
                if len(re.split(r"\s{2,}", line.strip())) >= 3:
                    cells = re.split(r"\s{2,}", line.strip())
                else:
                    cells = line.strip().split()
                parsed.append((line_no, cells))
        header_pos = self._find_header_row([cells for _, cells in parsed])
        if header_pos is None:
            return []
        headers = [normalize_header(value) for value in parsed[header_pos][1]]
        mapping = self._map_headers(headers)
        if not mapping:
            return []
        output: list[tuple[int, dict[str, str]]] = []
        for line_no, cells in parsed[header_pos + 1 :]:
            if not any(str(cell).strip() for cell in cells):
                continue
            row = {headers[i]: str(cells[i]).strip() if i < len(cells) else "" for i in range(len(headers))}
            if self._looks_like_data_row(mapping, row):
                output.append((line_no, row))
        return output

    def _read_key_value_blocks(self, path: Path, text: str) -> list[tuple[int, dict[str, str]]]:
        output: list[tuple[int, dict[str, str]]] = []
        blocks = re.split(r"\n\s*\n", text)
        line_cursor = 1
        for block in blocks:
            mapping: dict[str, str] = {}
            for line in block.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                elif "=" in line:
                    key, value = line.split("=", 1)
                else:
                    continue
                mapping[normalize_header(key)] = value.strip()
            if mapping and self._map_headers(list(mapping)):
                output.append((line_cursor, mapping))
            line_cursor += max(1, len(block.splitlines()) + 1)
        return output

    def _find_header_row(self, rows: list[list[str]]) -> int | None:
        aliases = {alias for values in ALIASES.values() for alias in values}
        best: tuple[int, int] | None = None
        for index, row in enumerate(rows[:30]):
            normalized = [normalize_header(value) for value in row]
            score = sum(
                1 for value in normalized
                if value in aliases or any(alias in value for alias in aliases if len(alias) >= 4)
            )
            if score >= 2 and (best is None or score > best[1]):
                best = (index, score)
        return best[0] if best else None

    def _map_headers(self, headers: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for field_name, aliases in ALIASES.items():
            for header in headers:
                if header in aliases or any(alias in header for alias in aliases if len(alias) >= 4):
                    result[field_name] = header
                    break
        return result

    def _looks_like_data_row(self, mapping: dict[str, str], row: dict[str, str]) -> bool:
        identity = str(row.get(mapping.get("string_no", ""), "") or row.get(mapping.get("serial", ""), "")).strip()
        measures = [
            row.get(mapping.get(name, ""), "")
            for name in ("noise", "resistance", "frequency", "damping", "sensitivity", "temperature", "distortion", "impedance")
        ]
        return bool(identity or any(to_float(value) is not None for value in measures))

    def _record_from_mapping(self, row: dict[str, str]) -> SmtTestRecord:
        header_map = self._map_headers(list(row))

        def get(name: str) -> str:
            return str(row.get(header_map.get(name, ""), "")).strip()

        date_text = get("tested_at")
        if not date_text:
            date_text = " ".join(part for part in (get("test_date"), get("test_clock")) if part).strip()
        string_no = get("string_no")
        serial = get("serial")
        if not string_no:
            string_no = serial
        return SmtTestRecord(
            string_no=string_no,
            serial=serial,
            tester=get("tester"),
            operator=get("operator"),
            original_tested_at=date_text,
            model=self._normalize_model(get("model")),
            source_result=get("source_result"),
            noise=to_float(get("noise")),
            resistance=to_float(get("resistance")),
            frequency=to_float(get("frequency")),
            damping=to_float(get("damping")),
            sensitivity=to_float(get("sensitivity")),
            temperature=to_float(get("temperature")),
            distortion=to_float(get("distortion")),
            impedance=to_float(get("impedance")),
            polarity=get("polarity"),
            notes=get("notes"),
        )

    @staticmethod
    def _normalize_model(value: str) -> str:
        text = value.strip().upper().replace("_", "-")
        compact = re.sub(r"[^A-Z0-9]", "", text)
        if "SGT" in compact:
            return "SGT-II"
        for model in ("SMT400", "SMT300", "SMT200"):
            if model in compact:
                return model
        return text

    @staticmethod
    def _infer_model(text: str) -> str:
        upper = text.upper()
        if "SGT-II" in upper or "SGT II" in upper or "SGT2" in upper:
            return "SGT-II"
        for model in ("SMT400", "SMT300", "SMT200"):
            if model in upper:
                return model
        return "SMT200"

    def _resolve_date(self, text: str, file_date: date, options: ImportOptions) -> tuple[datetime | None, str]:
        parsed = self._parse_datetime(text)
        valid = parsed is not None and parsed.year >= int(options.minimum_valid_year)
        if valid:
            return parsed, ""
        reason = "missing test date" if not text.strip() else f"invalid/old test date '{text}'"
        mode = options.bad_date_mode.lower().strip()
        if mode == "accept":
            return parsed, reason
        if mode == "reject":
            return None, reason
        if mode == "correct":
            replacement = options.replacement_date.lower().strip()
            if replacement == "today":
                resolved_date = date.today()
            elif replacement == "yesterday":
                resolved_date = date.today() - timedelta(days=1)
            else:
                resolved_date = file_date
            resolved_time = parsed.time() if parsed is not None else time(0, 0)
            return datetime.combine(resolved_date, resolved_time), reason + f"; corrected to {resolved_date.isoformat()}"
        # warn: preserve a parseable date even when old, otherwise use file date so the row remains queryable.
        if parsed is not None:
            return parsed, reason
        return datetime.combine(file_date, time(0, 0)), reason + f"; file date used for storage"

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        normalized = re.sub(r"\s+", " ", text.replace("T", " ")).strip()
        # ISO first, including timezone suffixes supported by fromisoformat.
        for candidate in (normalized, normalized.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate).replace(tzinfo=None)
            except ValueError:
                pass
        formats = (
            "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%y %H:%M:%S", "%d-%b-%y %H:%M",
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
            "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
            "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
            "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
        )
        for fmt in formats:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        # Numeric timestamps occasionally appear in instrument exports.
        if re.fullmatch(r"\d{10}(?:\.\d+)?", normalized):
            try:
                return datetime.fromtimestamp(float(normalized))
            except (OverflowError, OSError, ValueError):
                pass
        return None
