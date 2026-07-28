from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(slots=True)
class UpholeShot:
    file_name: str = ""
    shot_id: str = ""
    depth_m: float | None = None
    offset_m: float | None = None
    pick_ms: float | None = None
    corrected_ms: float | None = None
    channel: int | None = None
    sample_interval_ms: float | None = None
    samples: int | None = None
    trace_count: int | None = None
    source_line: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def _float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _int(value: object) -> int | None:
    f = _float(value)
    return int(f) if f is not None else None


_ALIASES: dict[str, tuple[str, ...]] = {
    "shot_id": ("shot", "shot_id", "file", "record", "record_no", "sp", "source_point"),
    "depth_m": ("depth", "depth_m", "hole_depth", "source_depth", "charge_depth"),
    "offset_m": ("offset", "offset_m", "channel_offset", "receiver_offset"),
    "pick_ms": ("pick", "pick_ms", "first_break", "first_break_ms", "fb", "time", "time_ms", "break_ms"),
    "corrected_ms": ("corrected", "corrected_ms", "corr_time", "corrected_time", "t_corr"),
    "channel": ("channel", "ch", "trace"),
    "sample_interval_ms": ("sample_interval", "sample_interval_ms", "dt", "dt_ms", "sample_rate"),
    "samples": ("samples", "num_samples", "ns", "sample_count"),
    "trace_count": ("traces", "trace_count", "channels", "num_channels"),
    "note": ("note", "remark", "remarks", "comment"),
}


class UpholeReader:
    """Lightweight SEG-2/OYO/table reader for uphole interpretation setup.

    It supports CSV/TXT depth-pick tables directly and extracts basic metadata
    from SEG-2/OYO-like files. Actual seismic sample decoding can be added as a
    later binary plugin, but this module already covers the legacy Uphole2
    operational workflow: file-depth assignment, picks and time-depth output.
    """

    def read(self, path: str | Path) -> list[UpholeShot]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        if p.is_dir():
            return self.read_folder(p)
        suffix = p.suffix.lower()
        if suffix in {".csv", ".txt", ".tsv", ".dat", ".fda", ".hol", ".cho"}:
            try:
                records = self._read_table(p)
                if records:
                    return records
            except Exception:
                pass
        return [self._read_binary_header(p)]

    def read_folder(self, folder: Path) -> list[UpholeShot]:
        records: list[UpholeShot] = []
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in {".sg2", ".seg2", ".dat", ".oyo", ".txt", ".csv", ".fda"}:
                try:
                    records.extend(self.read(path))
                except Exception as exc:
                    records.append(UpholeShot(file_name=path.name, note=f"Import warning: {exc}"))
        if not records:
            raise ValueError("No uphole-compatible files were found in the selected folder.")
        return records

    def _read_table(self, path: Path) -> list[UpholeShot]:
        raw = path.read_bytes()
        if b"\x00" in raw[:4096] and path.suffix.lower() not in {".dat"}:
            return []
        text = None
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            return []
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return []
        delimiter = None
        try:
            delimiter = csv.Sniffer().sniff("\n".join(lines[:15]), delimiters=",;\t|").delimiter
        except Exception:
            delimiter = None
        if delimiter:
            rows = list(csv.reader(lines, delimiter=delimiter))
        elif len(re.split(r"\s{2,}", lines[0])) >= 3:
            rows = [re.split(r"\s{2,}", line.strip()) for line in lines]
        else:
            rows = [line.split() for line in lines]
        header_idx, mapping = self._find_mapping(rows)
        if header_idx is None:
            return []
        headers = [_norm(h) for h in rows[header_idx]]
        output: list[UpholeShot] = []
        for line_no, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
            data = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            rec = UpholeShot(
                file_name=path.name,
                shot_id=str(data.get(mapping.get("shot_id", ""), "")).strip(),
                depth_m=_float(data.get(mapping.get("depth_m", ""))),
                offset_m=_float(data.get(mapping.get("offset_m", ""))),
                pick_ms=_float(data.get(mapping.get("pick_ms", ""))),
                corrected_ms=_float(data.get(mapping.get("corrected_ms", ""))),
                channel=_int(data.get(mapping.get("channel", ""))),
                sample_interval_ms=_float(data.get(mapping.get("sample_interval_ms", ""))),
                samples=_int(data.get(mapping.get("samples", ""))),
                trace_count=_int(data.get(mapping.get("trace_count", ""))),
                note=str(data.get(mapping.get("note", ""), "")).strip(),
                source_line=line_no,
            )
            if rec.depth_m is not None or rec.pick_ms is not None or rec.corrected_ms is not None or rec.shot_id:
                output.append(rec)
        return output

    def _find_mapping(self, rows: list[list[str]]) -> tuple[int | None, dict[str, str]]:
        alias_words = {a for aliases in _ALIASES.values() for a in aliases}
        best_idx: int | None = None; best_map: dict[str, str] = {}; best_score = 0
        for i, row in enumerate(rows[:20]):
            headers = [_norm(c) for c in row]
            mapping: dict[str, str] = {}
            for field, aliases in _ALIASES.items():
                for h in headers:
                    if h in aliases or any(alias in h for alias in aliases if len(alias) > 3):
                        mapping[field] = h; break
            score = len(mapping)
            if score > best_score and ("depth_m" in mapping or "pick_ms" in mapping or "corrected_ms" in mapping):
                best_idx, best_map, best_score = i, mapping, score
        return best_idx, best_map

    def _read_binary_header(self, path: Path) -> UpholeShot:
        raw = path.read_bytes()[:65536]
        text = raw.decode("latin-1", errors="ignore")
        sample_interval = None; samples = None; traces = None
        patterns = {
            "sample_interval_ms": r"(?:SAMPLE[_ -]?INTERVAL|DT)\D+(\d+(?:\.\d+)?)",
            "samples": r"(?:SAMPLES|NUM[_ -]?SAMPLES|NS)\D+(\d+)",
            "trace_count": r"(?:TRACES|CHANNELS|NUM[_ -]?CHANNELS)\D+(\d+)",
        }
        sample_interval = _float(re.search(patterns["sample_interval_ms"], text, re.I).group(1)) if re.search(patterns["sample_interval_ms"], text, re.I) else None
        samples = _int(re.search(patterns["samples"], text, re.I).group(1)) if re.search(patterns["samples"], text, re.I) else None
        traces = _int(re.search(patterns["trace_count"], text, re.I).group(1)) if re.search(patterns["trace_count"], text, re.I) else None
        note = "SEG-2/OYO header imported; assign depth and pick first break in the table."
        if b"SEG-2" in raw.upper() or path.suffix.lower() in {".sg2", ".seg2"}:
            note = "SEG-2 file detected; metadata imported. Add depth/picks for interpretation."
        return UpholeShot(file_name=path.name, shot_id=path.stem, sample_interval_ms=sample_interval, samples=samples, trace_count=traces, note=note)
