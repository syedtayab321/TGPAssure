from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class SmtRecord:
    serial: str = ""
    string_id: str = ""
    tester: str = ""
    operator: str = ""
    test_time: str = ""
    noise: float | None = None
    resistance: float | None = None
    distortion: float | None = None
    frequency: float | None = None
    damping: float | None = None
    sensitivity: float | None = None
    impedance: float | None = None
    polarity: str = ""
    note: str = ""
    source_file: str = ""
    source_line: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_ALIASES: dict[str, tuple[str, ...]] = {
    "serial": ("serial", "serial_no", "serial_number", "sn", "sensor", "geophone", "geophone_sn", "string_no", "string"),
    "string_id": ("string_id", "string", "line_string", "receiver", "station", "channel"),
    "tester": ("tester", "tester_no", "tester_id", "smt", "smt_no", "instrument"),
    "operator": ("operator", "user", "tested_by", "technician"),
    "test_time": ("date", "time", "datetime", "test_time", "test_date", "tested_at"),
    "noise": ("noise", "noise_mv", "noise_uv", "rms_noise", "nois"),
    "resistance": ("resistance", "res", "ohm", "ohms", "coil_resistance", "coil_res"),
    "distortion": ("distortion", "dist", "thd", "harmonic", "harmonic_distortion"),
    "frequency": ("frequency", "freq", "natural_frequency", "fn", "hz"),
    "damping": ("damping", "damp", "damping_ratio"),
    "sensitivity": ("sensitivity", "sens", "mv_per_ms", "v_m_s", "output"),
    "impedance": ("impedance", "imp", "z", "imp_ohm"),
    "polarity": ("polarity", "polar", "phase", "reverse", "reversed"),
    "note": ("note", "notes", "remark", "remarks", "comment", "status"),
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


class SmtReader:
    """Reader for SMT-200/SMT-300 style geophone/string tester exports.

    The legacy SMTAN utility accepted vendor tester output and built a DBF-based
    QC database. This reader keeps the same domain fields but accepts modern
    CSV/TXT/TSV exports and whitespace-delimited reports. Proprietary binary
    tester dumps are detected and reported clearly instead of failing silently.
    """

    def read(self, file_path: str | Path) -> list[SmtRecord]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        if raw[:2] == b"MZ" or (b"\x00" in raw[:2048] and path.suffix.lower() not in {".dbf"}):
            raise ValueError("This looks like a binary/proprietary SMT file. Export it to CSV/TXT from the tester software or convert it before import.")
        text = _read_text(path)
        records = self._read_table_text(path, text)
        if not records:
            records = self._read_key_value_blocks(path, text)
        if not records:
            raise ValueError("No SMT/geophone tester rows were recognized. Expected serial/resistance/noise/frequency/damping fields.")
        return records

    def _read_table_text(self, path: Path, text: str) -> list[SmtRecord]:
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return []
        sample = "\n".join(lines[:20])
        delimiter = None
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except Exception:
            pass
        if delimiter is None:
            header_line = lines[0]
            if len(re.split(r"\s{2,}", header_line.strip())) >= 3:
                delimiter = "multi_space"
            elif len(header_line.split()) >= 5:
                delimiter = "space"
            else:
                return []
        if delimiter == "multi_space":
            rows = [re.split(r"\s{2,}", line.strip()) for line in lines]
        elif delimiter == "space":
            rows = [line.split() for line in lines]
        else:
            rows = list(csv.reader(lines, delimiter=delimiter))
        if len(rows) < 2:
            return []
        header_idx = self._find_header_row(rows)
        if header_idx is None:
            return []
        headers = [_norm(h) for h in rows[header_idx]]
        mapping = self._map_headers(headers)
        if not mapping:
            return []
        output: list[SmtRecord] = []
        for idx, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
            if not any(cell.strip() for cell in row if isinstance(cell, str)):
                continue
            data = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            rec = self._record_from_row(mapping, data)
            rec.source_file = path.name
            rec.source_line = idx
            if rec.serial or rec.string_id or any(getattr(rec, f) is not None for f in ("resistance", "noise", "frequency", "damping")):
                output.append(rec)
        return output

    def _find_header_row(self, rows: list[list[str]]) -> int | None:
        best: tuple[int, int] | None = None
        alias_words = {alias for aliases in _ALIASES.values() for alias in aliases}
        for i, row in enumerate(rows[:20]):
            normalized = [_norm(c) for c in row]
            score = sum(1 for h in normalized if h in alias_words or any(a in h for a in alias_words if len(a) > 3))
            if score >= 2 and (best is None or score > best[1]):
                best = (i, score)
        return best[0] if best else None

    def _map_headers(self, headers: list[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for field, aliases in _ALIASES.items():
            for header in headers:
                if header in aliases or any(alias in header for alias in aliases if len(alias) > 3):
                    mapping[field] = header
                    break
        return mapping

    def _record_from_row(self, mapping: dict[str, str], row: dict[str, str]) -> SmtRecord:
        def get(field: str) -> str:
            return str(row.get(mapping.get(field, ""), "")).strip()
        return SmtRecord(
            serial=get("serial"),
            string_id=get("string_id"),
            tester=get("tester"),
            operator=get("operator"),
            test_time=get("test_time"),
            noise=_to_float(get("noise")),
            resistance=_to_float(get("resistance")),
            distortion=_to_float(get("distortion")),
            frequency=_to_float(get("frequency")),
            damping=_to_float(get("damping")),
            sensitivity=_to_float(get("sensitivity")),
            impedance=_to_float(get("impedance")),
            polarity=get("polarity"),
            note=get("note"),
        )

    def _read_key_value_blocks(self, path: Path, text: str) -> list[SmtRecord]:
        blocks = re.split(r"\n\s*\n", text)
        records: list[SmtRecord] = []
        for block_no, block in enumerate(blocks, start=1):
            pairs: dict[str, str] = {}
            for line in block.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                elif "=" in line:
                    key, value = line.split("=", 1)
                else:
                    continue
                pairs[_norm(key)] = value.strip()
            if not pairs:
                continue
            mapping = self._map_headers(list(pairs))
            if not mapping:
                continue
            rec = self._record_from_row(mapping, pairs)
            rec.source_file = path.name
            rec.source_line = block_no
            records.append(rec)
        return records
