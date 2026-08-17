from __future__ import annotations

import csv
import re
import struct
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
    "file_name": ("file_name", "filename", "file", "seg2_file", "sg2_file", "oyo_file", "trace_file"),
    "shot_id": ("shot", "shot_id", "record", "record_no", "sp", "source_point"),
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

_SEG2_FILE_MAGIC = {b"\x55\x3a", b"\x3a\x55"}
_SEG2_TRACE_MAGIC = {b"\x22\x44", b"\x44\x22"}
_TEXT_TABLE_SUFFIXES = {".gen", ".csv", ".txt", ".tsv", ".dat", ".fda", ".hol", ".cho"}
_UPHOLE_BINARY_SUFFIXES = {".sg2", ".seg2", ".oyo"}


class UpholeReader:
    """Legacy-style SEG-2/OYO/table reader for uphole interpretation.

    The old UYH/PowerBASIC uphole program only accepts proper SEG-2 or OYO
    files. This reader follows the same rule for .sg2/.seg2/.oyo imports:
    it no longer accepts a plain text file just because the extension is .seg2.
    CSV/TXT pick tables are still supported for TGPAssure interpretation work.
    """

    invalid_format_message = "File is not SEG2 or OYO format, cannot load it"

    def read(self, path: str | Path) -> list[UpholeShot]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        if p.is_dir():
            return self.read_folder(p)

        suffix = p.suffix.lower()
        if suffix in _TEXT_TABLE_SUFFIXES:
            records = self._read_table(p)
            if records:
                return records
            if suffix in {".gen", ".csv", ".txt", ".tsv"}:
                raise ValueError("No depth/pick records were found in the selected table/GEN manifest.")

        if suffix in _UPHOLE_BINARY_SUFFIXES:
            return [self._read_binary_header(p)]

        # Allow auto-detection for files without a useful extension.
        return [self._read_binary_header(p)]

    def read_folder(self, folder: Path) -> list[UpholeShot]:
        records: list[UpholeShot] = []
        files = [path for path in sorted(folder.iterdir()) if path.is_file()]
        gen_files = [path for path in files if path.suffix.lower() == ".gen"]
        binary_files = [path for path in files if path.suffix.lower() in _UPHOLE_BINARY_SUFFIXES]
        table_files = [path for path in files if path.suffix.lower() in _TEXT_TABLE_SUFFIXES]

        # Legacy uphole workflow: "Load a Hole" can be a GEN manifest plus SEG-2/OYO shot files.
        # If a GEN file exists, use it as the hole manifest; otherwise load the SEG-2/OYO shot files.
        # If no binary shot files exist, fall back to CSV/TXT/DAT-style pick tables.
        load_set = gen_files if gen_files else (binary_files if binary_files else table_files)
        for path in load_set:
            try:
                records.extend(self.read(path))
            except Exception as exc:
                records.append(UpholeShot(file_name=path.name, note=f"Import warning: {exc}"))
        if not records:
            raise ValueError("No uphole-compatible SEG-2/OYO/table files were found in the selected folder.")
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
            listed_file = str(data.get(mapping.get("file_name", ""), "")).strip()
            rec = UpholeShot(
                file_name=listed_file or path.name,
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
        best_idx: int | None = None
        best_map: dict[str, str] = {}
        best_score = 0
        for i, row in enumerate(rows[:20]):
            headers = [_norm(c) for c in row]
            mapping: dict[str, str] = {}
            for field, aliases in _ALIASES.items():
                for h in headers:
                    if h in aliases or any(alias in h for alias in aliases if len(alias) > 3):
                        mapping[field] = h
                        break
            score = len(mapping)
            if score > best_score and ("depth_m" in mapping or "pick_ms" in mapping or "corrected_ms" in mapping):
                best_idx, best_map, best_score = i, mapping, score
        return best_idx, best_map

    def _read_binary_header(self, path: Path) -> UpholeShot:
        raw = path.read_bytes()
        if self._is_seg2(raw):
            return self._read_seg2_header(path, raw)
        if self._is_oyo(raw):
            return self._read_oyo_header(path, raw)
        raise ValueError(self.invalid_format_message)

    @staticmethod
    def _is_seg2(raw: bytes) -> bool:
        if len(raw) < 32:
            return False
        if raw[:2] in _SEG2_FILE_MAGIC:
            return True
        # Some field systems leave SEG-2 text in the first descriptor strings.
        return b"SEG-2" in raw[:4096].upper() and any(m in raw[:4096] for m in _SEG2_TRACE_MAGIC)

    @staticmethod
    def _is_oyo(raw: bytes) -> bool:
        head = raw[:4096].decode("latin-1", errors="ignore").upper()
        return any(token in head for token in ("OYO", "MCSEIS", "GEOSPACE")) and any(
            token in head for token in ("SAMPLE", "TRACE", "CHANNEL", "SHOT", "DEPTH", "UPHOLE")
        )

    def _read_seg2_header(self, path: Path, raw: bytes) -> UpholeShot:
        little = raw[:2] == b"\x55\x3a"
        endian = "<" if little else ">"
        trace_count = None
        samples = None
        sample_interval = None
        note_parts = ["SEG-2 file detected"]

        if len(raw) >= 32:
            try:
                # Standard SEG-2 file descriptor: magic, revision, trace-pointer sub-block size, trace count.
                trace_count = struct.unpack(endian + "H", raw[6:8])[0]
                if trace_count <= 0 or trace_count > 4096:
                    trace_count = None
            except Exception:
                trace_count = None

        text = raw[:65536].decode("latin-1", errors="ignore")
        sample_interval = self._extract_sample_interval_ms(text)
        samples = self._extract_int(text, ("SAMPLES", "NUM_SAMPLES", "NS", "NUMBER_OF_SAMPLES"))
        if trace_count is None:
            trace_count = self._extract_int(text, ("TRACES", "CHANNELS", "NUM_CHANNELS", "NUMBER_OF_TRACES"))

        # Fallback: count visible trace descriptor magic blocks.
        if trace_count is None:
            count = sum(raw.count(magic) for magic in _SEG2_TRACE_MAGIC)
            trace_count = count or None

        if sample_interval is None:
            note_parts.append("sample interval not found")
        if samples is None:
            note_parts.append("sample count not found")

        return UpholeShot(
            file_name=path.name,
            shot_id=path.stem,
            sample_interval_ms=sample_interval,
            samples=samples,
            trace_count=trace_count,
            note="; ".join(note_parts) + "; assign depth and first-break pick for interpretation.",
        )

    def _read_oyo_header(self, path: Path, raw: bytes) -> UpholeShot:
        text = raw[:65536].decode("latin-1", errors="ignore")
        return UpholeShot(
            file_name=path.name,
            shot_id=self._extract_text(text, ("SHOT", "SHOT_ID", "RECORD")) or path.stem,
            depth_m=self._extract_float_after(text, ("DEPTH", "CHARGE_DEPTH", "HOLE_DEPTH")),
            offset_m=self._extract_float_after(text, ("OFFSET", "RECEIVER_OFFSET")),
            pick_ms=self._extract_float_after(text, ("PICK", "FIRST_BREAK", "FB")),
            sample_interval_ms=self._extract_sample_interval_ms(text),
            samples=self._extract_int(text, ("SAMPLES", "NUM_SAMPLES", "NS")),
            trace_count=self._extract_int(text, ("TRACES", "CHANNELS", "NUM_CHANNELS")),
            note="OYO uphole file detected; assign/check depth and first-break pick for interpretation.",
        )

    @staticmethod
    def _extract_int(text: str, labels: tuple[str, ...]) -> int | None:
        for label in labels:
            m = re.search(rf"\b{re.escape(label)}\b\D+(\d+)", text, re.I)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    return None
        return None

    @staticmethod
    def _extract_float_after(text: str, labels: tuple[str, ...]) -> float | None:
        for label in labels:
            m = re.search(rf"\b{re.escape(label)}\b\D+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", text, re.I)
            if m:
                return _float(m.group(1))
        return None

    @staticmethod
    def _extract_text(text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            m = re.search(rf"\b{re.escape(label)}\b\D+([A-Za-z0-9_.-]+)", text, re.I)
            if m:
                return m.group(1).strip()
        return None

    def _extract_sample_interval_ms(self, text: str) -> float | None:
        value = self._extract_float_after(text, ("SAMPLE_INTERVAL", "SAMPLE INTERVAL", "DT", "SI"))
        if value is None:
            return None
        # SEG-2 files commonly store DELTA/SAMPLE_INTERVAL in seconds. If the
        # value is very small, convert to ms for the uphole table.
        if 0 < value < 0.1:
            return value * 1000.0
        return value
