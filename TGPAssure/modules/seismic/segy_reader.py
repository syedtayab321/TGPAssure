from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np


ProgressCallback = Optional[Callable[[float, str], None]]
CancelCheck = Optional[Callable[[], bool]]


class UnsupportedSampleFormatError(ValueError):
    """Raised when a structurally plausible SEG-Y declares an unsupported format."""

    def __init__(self, format_code: int) -> None:
        self.format_code = int(format_code)
        super().__init__(f"Unsupported SEG-Y sample format code: {self.format_code}")


@dataclass(frozen=True)
class SegyTextHeader:
    raw: bytes
    encoding: str
    text: str
    lines: Tuple[str, ...]

    @property
    def decoded_text(self) -> str:
        """Compatibility alias retained for older consumers."""
        return self.text


@dataclass(frozen=True)
class SegyBinaryHeader:
    endian: str
    job_id: int
    line_number: int
    reel_number: int
    data_traces_per_ensemble: int
    auxiliary_traces_per_ensemble: int
    sample_interval_us: float
    original_sample_interval_us: float
    samples_per_trace: int
    original_samples_per_trace: int
    sample_format_code: int
    ensemble_fold: int
    trace_sorting_code: int
    vertical_sum_code: int
    sweep_frequency_start_hz: int
    sweep_frequency_end_hz: int
    sweep_length_ms: int
    sweep_type_code: int
    measurement_system: int
    segy_revision_major: int
    segy_revision_minor: int
    fixed_length_trace_flag: int
    extended_text_header_count: int
    byte_order_sentinel: int = 0
    byte_order_detection: str = "heuristic"
    maximum_additional_trace_headers: int = 0
    survey_type_code: int = 0
    time_basis_code: int = 0
    declared_trace_count: int = 0
    first_trace_offset: int = 0
    data_trailer_stanza_count: int = 0

    @property
    def revision(self) -> str:
        return f"{self.segy_revision_major}.{self.segy_revision_minor}"

    @property
    def trace_count(self) -> int:
        """Legacy alias; standard SEG-Y does not store total file trace count."""
        return int(self.data_traces_per_ensemble)

    @property
    def sample_count_per_trace(self) -> int:
        return int(self.samples_per_trace)

    @property
    def sample_interval_ms(self) -> float:
        return float(self.sample_interval_us) / 1000.0


@dataclass(frozen=True)
class SegyTraceHeader:
    trace_sequence_line: int
    trace_sequence_file: int
    field_record: int
    trace_number: int
    energy_source_point: int
    cdp: int
    cdp_trace: int
    trace_identification: int
    offset: float
    elevation_scalar: int
    coordinate_scalar: int
    source_x: float
    source_y: float
    receiver_x: float
    receiver_y: float
    coordinate_units: int
    source_static_ms: int
    receiver_static_ms: int
    total_static_ms: int
    delay_time_ms: int
    sample_count: int
    sample_interval_us: float
    year: int
    day_of_year: int
    hour: int
    minute: int
    second: int
    cdp_x: float
    cdp_y: float
    inline_3d: int
    crossline_3d: int
    shotpoint: int


@dataclass
class SegyTraceIndex:
    byte_offsets: np.ndarray
    header_sizes: np.ndarray
    trace_extension_counts: np.ndarray
    trace_extension_1_present: np.ndarray
    sample_counts: np.ndarray
    sample_intervals_us: np.ndarray
    trace_sequence_line: np.ndarray
    trace_sequence_file: np.ndarray
    field_record: np.ndarray
    trace_number: np.ndarray
    energy_source_point: np.ndarray
    cdp: np.ndarray
    cdp_trace: np.ndarray
    trace_identification: np.ndarray
    offsets: np.ndarray
    elevation_scalar: np.ndarray
    coordinate_scalar: np.ndarray
    source_x_raw: np.ndarray
    source_y_raw: np.ndarray
    receiver_x_raw: np.ndarray
    receiver_y_raw: np.ndarray
    source_x: np.ndarray
    source_y: np.ndarray
    receiver_x: np.ndarray
    receiver_y: np.ndarray
    coordinate_units: np.ndarray
    source_static_ms: np.ndarray
    receiver_static_ms: np.ndarray
    total_static_ms: np.ndarray
    delay_time_ms: np.ndarray
    year: np.ndarray
    day_of_year: np.ndarray
    hour: np.ndarray
    minute: np.ndarray
    second: np.ndarray
    cdp_x_raw: np.ndarray
    cdp_y_raw: np.ndarray
    cdp_x: np.ndarray
    cdp_y: np.ndarray
    inline_3d: np.ndarray
    crossline_3d: np.ndarray
    shotpoint: np.ndarray
    trace_end_offset: int
    trailing_bytes: int
    truncated: bool

    @property
    def trace_count(self) -> int:
        return int(self.byte_offsets.size)


class SegyReader:
    """Memory-efficient SEG-Y Rev 0/1/2 reader used by the QC pipeline.

    The reader supports big- and little-endian files, ASCII and EBCDIC textual
    headers, fixed or variable trace lengths, extended textual headers and the
    commonly used SEG-Y sample formats.
    """

    TEXT_HEADER_BYTES = 3200
    BINARY_HEADER_BYTES = 400
    TRACE_HEADER_BYTES = 240
    BASE_TRACE_OFFSET = 3600

    SAMPLE_FORMATS: Dict[int, Tuple[str, int]] = {
        1: ("IBM 32-bit float", 4),
        2: ("32-bit signed integer", 4),
        3: ("16-bit signed integer", 2),
        5: ("IEEE 32-bit float", 4),
        6: ("IEEE 64-bit float", 8),
        7: ("24-bit signed integer", 3),
        8: ("8-bit signed integer", 1),
        9: ("64-bit signed integer", 8),
        10: ("32-bit unsigned integer", 4),
        11: ("16-bit unsigned integer", 2),
        12: ("64-bit unsigned integer", 8),
        15: ("24-bit unsigned integer", 3),
        16: ("8-bit unsigned integer", 1),
    }

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path).expanduser().resolve()
        if not self.file_path.exists():
            raise FileNotFoundError(f"SEG-Y file not found: {self.file_path}")
        if not self.file_path.is_file():
            raise ValueError(f"SEG-Y path is not a file: {self.file_path}")
        self.file_size = self.file_path.stat().st_size
        if self.file_size < self.BASE_TRACE_OFFSET:
            raise ValueError("The file is smaller than the mandatory 3600-byte SEG-Y header")

        with self.file_path.open("rb") as handle:
            self._text_raw = handle.read(self.TEXT_HEADER_BYTES)
            self._binary_raw = handle.read(self.BINARY_HEADER_BYTES)

        self.text_header = self._decode_text_header(self._text_raw)
        self._legacy_compact_header = False
        self.binary_header = self._parse_binary_header(self._binary_raw)
        if self.binary_header.sample_format_code not in self.SAMPLE_FORMATS:
            raise UnsupportedSampleFormatError(self.binary_header.sample_format_code)
        self.sample_format_name, self.bytes_per_sample = self.SAMPLE_FORMATS[
            self.binary_header.sample_format_code
        ]
        self.trace_header_bytes = self.TRACE_HEADER_BYTES
        ext_count = self.binary_header.extended_text_header_count
        self.extended_header_count_unknown = ext_count < 0
        self.extended_header_count = (
            self._resolve_variable_extended_header_count() if ext_count < 0 else max(0, ext_count)
        )
        computed_trace_start = self.BASE_TRACE_OFFSET + self.extended_header_count * self.TEXT_HEADER_BYTES
        declared_trace_start = int(self.binary_header.first_trace_offset)
        if declared_trace_start > 0 and declared_trace_start >= computed_trace_start:
            self.trace_data_start = declared_trace_start
            self.trace_data_start_source = "binary-header-override"
        elif declared_trace_start > 0:
            # Preserve the invalid declaration for QC, but never index traces inside the
            # mandatory textual/binary/extended textual header region.
            self.trace_data_start = computed_trace_start
            self.trace_data_start_source = "invalid-binary-header-override-fallback"
        else:
            self.trace_data_start = computed_trace_start
            self.trace_data_start_source = "computed-from-text-headers"
        if self.trace_data_start > self.file_size:
            raise ValueError("SEG-Y trace-data start points beyond the end of the file")
        if self._legacy_compact_header:
            self.trace_header_bytes = self._infer_legacy_trace_header_bytes()
        self.extended_text_headers = self._read_extended_headers()
        self._trace_index: Optional[SegyTraceIndex] = None

    @staticmethod
    def _i16(data: bytes, offset: int, endian: str) -> int:
        return int.from_bytes(data[offset:offset + 2], "big" if endian == ">" else "little", signed=True)

    @staticmethod
    def _u16(data: bytes, offset: int, endian: str) -> int:
        return int.from_bytes(data[offset:offset + 2], "big" if endian == ">" else "little", signed=False)

    @staticmethod
    def _i32(data: bytes, offset: int, endian: str) -> int:
        return int.from_bytes(data[offset:offset + 4], "big" if endian == ">" else "little", signed=True)

    @staticmethod
    def _u32(data: bytes, offset: int, endian: str) -> int:
        return int.from_bytes(data[offset:offset + 4], "big" if endian == ">" else "little", signed=False)

    @staticmethod
    def _i64(data: bytes, offset: int, endian: str) -> int:
        return int.from_bytes(data[offset:offset + 8], "big" if endian == ">" else "little", signed=True)

    @staticmethod
    def _u64(data: bytes, offset: int, endian: str) -> int:
        return int.from_bytes(data[offset:offset + 8], "big" if endian == ">" else "little", signed=False)

    @staticmethod
    def _f64(data: bytes, offset: int, endian: str) -> float:
        import struct
        return float(struct.unpack((">" if endian == ">" else "<") + "d", data[offset:offset + 8])[0])

    @staticmethod
    def _decode_text_header(raw: bytes) -> SegyTextHeader:
        ascii_text = raw.decode("ascii", errors="replace")
        ebcdic_text = raw.decode("cp500", errors="replace")

        def score(value: str) -> float:
            printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in value)
            replacements = value.count("�")
            c_prefix = sum(
                1 for i in range(0, min(len(value), 3200), 80)
                if value[i:i + 3].strip().upper().startswith("C")
            )
            common = sum(value.upper().count(word) for word in ("CLIENT", "LINE", "REEL", "SAMPLE", "SEG-Y", "SEGY"))
            return printable - replacements * 20 + c_prefix * 15 + common * 10

        if score(ascii_text) >= score(ebcdic_text):
            encoding = "ASCII"
            decoded = ascii_text
        else:
            encoding = "EBCDIC cp500"
            decoded = ebcdic_text

        lines = tuple(decoded[i:i + 80].rstrip() for i in range(0, 3200, 80))
        return SegyTextHeader(raw=raw, encoding=encoding, text="\n".join(lines), lines=lines)

    def _detect_endian(self, data: bytes) -> tuple[str, int, str]:
        """Detect SEG-Y byte order, preferring the Rev 2 endian sentinel.

        SEG-Y Rev 2.x reserves binary-header bytes 3297-3300 for 0x01020304.
        Older files frequently leave the sentinel at zero, so a conservative
        plausibility fallback is retained for Rev 0/1 compatibility. Pairwise
        byte-swapped files are detected explicitly and rejected rather than
        silently decoded with corrupted sample/header values.
        """
        sentinel_raw = data[96:100]
        if sentinel_raw == b"\x01\x02\x03\x04":
            return ">", 0x01020304, "rev2-sentinel-big-endian"
        if sentinel_raw == b"\x04\x03\x02\x01":
            return "<", 0x01020304, "rev2-sentinel-little-endian"
        if sentinel_raw == b"\x02\x01\x04\x03":
            raise ValueError(
                "SEG-Y uses consecutive byte-pair swapping (endian sentinel 0x02010403); "
                "normalize the byte stream before scientific interpretation to avoid silent corruption"
            )

        candidates: List[Tuple[int, str]] = []
        for endian in (">", "<"):
            sample_interval = float(self._u16(data, 16, endian))
            samples = int(self._u16(data, 20, endian))
            sample_format = self._u16(data, 24, endian)
            revision = self._u16(data, 300, endian)
            revision_major = (revision >> 8) & 0xFF
            if revision in (1, 2):
                revision_major = revision
            # Rev 1+ may legitimately use zero in the legacy 16-bit timing/count
            # fields and place the controlling values in bytes 3269-3280.
            if revision_major >= 1:
                extended_samples = self._u32(data, 68, endian)
                extended_dt = self._f64(data, 72, endian)
                if extended_samples:
                    samples = int(extended_samples)
                if math.isfinite(extended_dt) and extended_dt > 0.0:
                    sample_interval = float(extended_dt)
            fixed_flag = self._u16(data, 302, endian)
            score = 0
            if sample_format in self.SAMPLE_FORMATS:
                score += 8
            if 0.0 < sample_interval <= 1_000_000_000.0:
                score += 3
            if 1 <= samples <= 0xFFFFFFFF:
                score += 3
            if revision in (0, 0x0100, 0x0200, 0x0001, 0x0002, 0x0201):
                score += 2
            if fixed_flag in (0, 1):
                score += 1
            candidates.append((score, endian))
        candidates.sort(reverse=True)
        if not candidates or candidates[0][0] < 8:
            raise ValueError("Unable to determine SEG-Y byte order from the binary header")
        return candidates[0][1], int.from_bytes(sentinel_raw, "big", signed=False), "heuristic-pre-rev2-or-zero-sentinel"

    def _parse_legacy_compact_header(self, data: bytes) -> SegyBinaryHeader | None:
        """Recognize the compact header used by early TGPAssure prototypes/tests.

        This is deliberately only attempted after standard SEG-Y byte-order
        detection fails, so a valid SEG-Y file can never be downgraded to this
        compatibility path.
        """
        for endian in (">", "<"):
            sample_format = self._u16(data, 0, endian)
            trace_count = self._u16(data, 2, endian)
            sample_count = self._u16(data, 4, endian)
            interval_ms = self._u16(data, 6, endian)
            if sample_format not in self.SAMPLE_FORMATS:
                continue
            if not (1 <= trace_count <= 10_000_000 and 1 <= sample_count <= 1_000_000 and 1 <= interval_ms <= 60_000):
                continue
            self._legacy_compact_header = True
            interval_us = int(interval_ms) * 1000
            return SegyBinaryHeader(
                endian=endian, job_id=0, line_number=0, reel_number=0,
                data_traces_per_ensemble=trace_count, auxiliary_traces_per_ensemble=0,
                sample_interval_us=interval_us, original_sample_interval_us=interval_us,
                samples_per_trace=sample_count, original_samples_per_trace=sample_count,
                sample_format_code=sample_format, ensemble_fold=0, trace_sorting_code=0,
                vertical_sum_code=0, sweep_frequency_start_hz=0, sweep_frequency_end_hz=0,
                sweep_length_ms=0, sweep_type_code=0, measurement_system=0,
                segy_revision_major=0, segy_revision_minor=0, fixed_length_trace_flag=1,
                extended_text_header_count=0,
                byte_order_sentinel=0, byte_order_detection="legacy-compact",
            )
        return None

    def _plausible_legacy_compact_format_code(self, data: bytes) -> int | None:
        """Return a compact-header format code when the surrounding fields are plausible.

        Early TGPAssure prototype fixtures stored format/count/ns/dt in the first
        eight binary-header bytes. This detector is only used to produce a precise
        unsupported-format diagnostic after standard parsing has already failed.
        """
        for endian in (">", "<"):
            format_code = self._u16(data, 0, endian)
            trace_count = self._u16(data, 2, endian)
            sample_count = self._u16(data, 4, endian)
            interval_ms = self._u16(data, 6, endian)
            if (1 <= trace_count <= 10_000_000 and 1 <= sample_count <= 1_000_000
                    and 1 <= interval_ms <= 60_000 and format_code > 0):
                return int(format_code)
        return None

    def _infer_legacy_trace_header_bytes(self) -> int:
        """Infer an early prototype trace-header width without affecting real SEG-Y.

        Legacy compact files encode an explicit total trace count. If file length
        exactly resolves to a constant header width, accept widths up to the SEG-Y
        240-byte standard. This keeps old project files readable while all normal
        SEG-Y files remain on the standards path.
        """
        trace_count = int(self.binary_header.data_traces_per_ensemble)
        sample_count = int(self.binary_header.samples_per_trace)
        if trace_count <= 0 or sample_count <= 0:
            return self.TRACE_HEADER_BYTES
        payload = self.file_size - self.trace_data_start
        sample_bytes = trace_count * sample_count * self.bytes_per_sample
        remainder = payload - sample_bytes
        if remainder >= 0 and remainder % trace_count == 0:
            candidate = remainder // trace_count
            if 0 <= candidate <= self.TRACE_HEADER_BYTES:
                return int(candidate)
        return self.TRACE_HEADER_BYTES

    def _parse_binary_header(self, data: bytes) -> SegyBinaryHeader:
        try:
            endian, byte_order_sentinel, byte_order_detection = self._detect_endian(data)
        except ValueError:
            legacy = self._parse_legacy_compact_header(data)
            if legacy is not None:
                return legacy
            compact_format = self._plausible_legacy_compact_format_code(data)
            if compact_format is not None and compact_format not in self.SAMPLE_FORMATS:
                raise UnsupportedSampleFormatError(compact_format)
            raise
        revision_raw = self._u16(data, 300, endian)
        revision_major = (revision_raw >> 8) & 0xFF
        revision_minor = revision_raw & 0xFF
        if revision_raw in (1, 2):
            revision_major, revision_minor = revision_raw, 0

        data_traces_per_ensemble = self._i16(data, 12, endian)
        auxiliary_traces_per_ensemble = self._i16(data, 14, endian)
        sample_interval_us = float(self._u16(data, 16, endian))
        original_sample_interval_us = float(self._u16(data, 18, endian))
        samples_per_trace = int(self._u16(data, 20, endian))
        original_samples_per_trace = int(self._u16(data, 22, endian))
        ensemble_fold = int(self._u16(data, 26, endian))

        # Rev 1+ extended binary-header fields override their legacy 16-bit
        # counterparts when non-zero (SEG-Y Rev 2.1, bytes 3261-3296).
        if revision_major >= 1:
            extended_data_traces = self._u32(data, 60, endian)
            extended_aux_traces = self._u32(data, 64, endian)
            extended_samples = self._u32(data, 68, endian)
            extended_dt = self._f64(data, 72, endian)
            extended_original_dt = self._f64(data, 80, endian)
            extended_original_samples = self._u32(data, 88, endian)
            extended_fold = self._u32(data, 92, endian)
            if extended_data_traces:
                data_traces_per_ensemble = int(extended_data_traces)
            if extended_aux_traces:
                auxiliary_traces_per_ensemble = int(extended_aux_traces)
            if extended_samples:
                samples_per_trace = int(extended_samples)
            if math.isfinite(extended_dt) and extended_dt > 0.0:
                sample_interval_us = float(extended_dt)
            if math.isfinite(extended_original_dt) and extended_original_dt > 0.0:
                original_sample_interval_us = float(extended_original_dt)
            if extended_original_samples:
                original_samples_per_trace = int(extended_original_samples)
            if extended_fold:
                ensemble_fold = int(extended_fold)

        return SegyBinaryHeader(
            endian=endian,
            job_id=self._i32(data, 0, endian),
            line_number=self._i32(data, 4, endian),
            reel_number=self._i32(data, 8, endian),
            data_traces_per_ensemble=data_traces_per_ensemble,
            auxiliary_traces_per_ensemble=auxiliary_traces_per_ensemble,
            sample_interval_us=sample_interval_us,
            original_sample_interval_us=original_sample_interval_us,
            samples_per_trace=samples_per_trace,
            original_samples_per_trace=original_samples_per_trace,
            sample_format_code=self._u16(data, 24, endian),
            ensemble_fold=ensemble_fold,
            trace_sorting_code=self._i16(data, 28, endian),
            vertical_sum_code=self._i16(data, 30, endian),
            sweep_frequency_start_hz=self._u16(data, 32, endian),
            sweep_frequency_end_hz=self._u16(data, 34, endian),
            sweep_length_ms=self._u16(data, 36, endian),
            sweep_type_code=self._i16(data, 38, endian),
            measurement_system=self._i16(data, 54, endian),
            segy_revision_major=revision_major,
            segy_revision_minor=revision_minor,
            fixed_length_trace_flag=self._u16(data, 302, endian),
            extended_text_header_count=self._i16(data, 304, endian),
            byte_order_sentinel=byte_order_sentinel,
            byte_order_detection=byte_order_detection,
            maximum_additional_trace_headers=self._u16(data, 306, endian),
            survey_type_code=self._i16(data, 308, endian),
            time_basis_code=self._i16(data, 310, endian),
            declared_trace_count=self._u64(data, 312, endian),
            first_trace_offset=self._u64(data, 320, endian),
            data_trailer_stanza_count=self._u32(data, 328, endian),
        )

    def _resolve_variable_extended_header_count(self) -> int:
        """Resolve Rev 1/2 variable extended headers terminated by ((SEG: EndText))."""
        available_blocks = max(0, (self.file_size - self.BASE_TRACE_OFFSET) // self.TEXT_HEADER_BYTES)
        if available_blocks == 0:
            raise ValueError(
                "Binary header declares a variable extended textual-header count, but no extended header is present"
            )
        maximum_blocks = min(available_blocks, 4096)
        with self.file_path.open("rb") as handle:
            handle.seek(self.BASE_TRACE_OFFSET)
            for block_number in range(1, maximum_blocks + 1):
                raw = handle.read(self.TEXT_HEADER_BYTES)
                if len(raw) != self.TEXT_HEADER_BYTES:
                    break
                decoded = self._decode_text_header(raw).text.upper()
                normalized = "".join(decoded.split())
                if "((SEG:ENDTEXT))" in normalized:
                    return block_number
        raise ValueError(
            "Variable extended textual headers do not contain the required ((SEG: EndText)) terminator"
        )

    def _read_extended_headers(self) -> Tuple[SegyTextHeader, ...]:
        if self.extended_header_count <= 0:
            return tuple()
        headers: List[SegyTextHeader] = []
        with self.file_path.open("rb") as handle:
            handle.seek(self.BASE_TRACE_OFFSET)
            for _ in range(self.extended_header_count):
                raw = handle.read(self.TEXT_HEADER_BYTES)
                if len(raw) != self.TEXT_HEADER_BYTES:
                    break
                headers.append(self._decode_text_header(raw))
        return tuple(headers)

    @staticmethod
    def _apply_scalar(values: np.ndarray, scalars: np.ndarray) -> np.ndarray:
        values_f = values.astype(np.float64, copy=False)
        scalars_f = scalars.astype(np.float64, copy=False)
        factors = np.ones_like(scalars_f)
        positive = scalars_f > 0
        negative = scalars_f < 0
        factors[positive] = scalars_f[positive]
        factors[negative] = 1.0 / np.abs(scalars_f[negative])
        return values_f * factors

    def file_info(self) -> Dict[str, Any]:
        binary = asdict(self.binary_header)
        binary.update(
            {
                "revision": self.binary_header.revision,
                "sample_format_name": self.sample_format_name,
                "bytes_per_sample": self.bytes_per_sample,
            }
        )
        return {
            "file_path": str(self.file_path),
            "file_name": self.file_path.name,
            "file_size": self.file_size,
            "text_encoding": self.text_header.encoding,
            "binary_header": binary,
            "extended_text_header_count": self.extended_header_count,
            "extended_header_count_unknown": self.extended_header_count_unknown,
            "trace_data_start": self.trace_data_start,
            "trace_data_start_source": self.trace_data_start_source,
        }

    def scan_trace_headers(
        self,
        progress_callback: ProgressCallback = None,
        cancel_check: CancelCheck = None,
        force: bool = False,
    ) -> SegyTraceIndex:
        """Index trace headers without loading seismic samples into memory.

        Rev 2 trace-header extensions are accounted for per trace. When the
        standardized ``SEG00001`` extension is present, extended-precision
        sequence/geometry/offset/sample-count/sample-interval values override
        the legacy 240-byte fields as required by SEG-Y Rev 2.1.
        """
        if self._trace_index is not None and not force:
            return self._trace_index

        keys = (
            "byte_offsets", "header_sizes", "trace_extension_counts", "trace_extension_1_present",
            "sample_counts", "sample_intervals_us", "trace_sequence_line",
            "trace_sequence_file", "field_record", "trace_number", "energy_source_point",
            "cdp", "cdp_trace", "trace_identification", "offsets", "elevation_scalar",
            "coordinate_scalar", "source_x_raw", "source_y_raw", "receiver_x_raw",
            "receiver_y_raw", "source_x_ext", "source_y_ext", "receiver_x_ext", "receiver_y_ext",
            "coordinate_units", "source_static_ms", "receiver_static_ms", "total_static_ms",
            "delay_time_ms", "year", "day_of_year", "hour", "minute", "second",
            "cdp_x_raw", "cdp_y_raw", "cdp_x_ext", "cdp_y_ext",
            "inline_3d", "crossline_3d", "shotpoint",
        )
        values: Dict[str, List[Any]] = {key: [] for key in keys}
        position = self.trace_data_start
        truncated = False
        declared_trailer_bytes = max(0, int(self.binary_header.data_trailer_stanza_count)) * self.TEXT_HEADER_BYTES
        trace_payload_end = self.file_size - declared_trailer_bytes
        if trace_payload_end < self.trace_data_start:
            raise ValueError("Declared SEG-Y data trailer stanzas overlap the trace-data region")
        total_payload = max(1, trace_payload_end - self.trace_data_start)
        endian = self.binary_header.endian
        declared_max_extensions = max(0, int(self.binary_header.maximum_additional_trace_headers))
        if declared_max_extensions > 4096:
            raise ValueError(
                f"Unreasonable SEG-Y additional trace-header count: {declared_max_extensions}"
            )

        with self.file_path.open("rb", buffering=1024 * 1024) as handle:
            trace_number = 0
            while position + self.trace_header_bytes <= trace_payload_end:
                if cancel_check and cancel_check():
                    raise InterruptedError("SEG-Y trace-header scan cancelled")
                handle.seek(position)
                header = handle.read(self.trace_header_bytes)
                if len(header) < self.trace_header_bytes:
                    truncated = True
                    break

                extension_count = 0
                extension_1_present = False
                extension_1: bytes | None = None
                header_size = self.trace_header_bytes

                if not self._legacy_compact_header and declared_max_extensions > 0:
                    handle.seek(position + self.TRACE_HEADER_BYTES)
                    candidate = handle.read(self.TRACE_HEADER_BYTES)
                    if len(candidate) < self.TRACE_HEADER_BYTES:
                        truncated = True
                        break
                    signature = candidate[232:240].rstrip(b"\x00 ").upper()
                    extension_1_present = signature == b"SEG00001"
                    extension_1 = candidate if extension_1_present else None
                    extension_count = declared_max_extensions
                    if extension_1_present:
                        per_trace_count = self._u16(candidate, 156, endian)
                        if per_trace_count > 0:
                            extension_count = per_trace_count
                    if extension_count > 4096:
                        raise ValueError(
                            f"Trace {trace_number + 1:,} declares an unreasonable "
                            f"additional trace-header count: {extension_count}"
                        )
                    header_size = self.TRACE_HEADER_BYTES * (1 + extension_count)
                    if position + header_size > trace_payload_end:
                        truncated = True
                        break

                if self._legacy_compact_header:
                    ns = int(self.binary_header.samples_per_trace)
                    dt = float(self.binary_header.sample_interval_us)
                else:
                    ns = self._u16(header, 114, endian) or int(self.binary_header.samples_per_trace)
                    dt = float(self._u16(header, 116, endian) or self.binary_header.sample_interval_us)
                    if extension_1 is not None:
                        ns_ext = self._u32(extension_1, 136, endian)
                        dt_ext = self._f64(extension_1, 144, endian)
                        if ns_ext > 0:
                            ns = int(ns_ext)
                        if math.isfinite(dt_ext) and dt_ext > 0:
                            dt = float(dt_ext)
                if ns <= 0 or dt <= 0:
                    truncated = True
                    break
                trace_size = header_size + ns * self.bytes_per_sample
                if position + trace_size > trace_payload_end:
                    truncated = True
                    break

                values["byte_offsets"].append(position)
                values["header_sizes"].append(header_size)
                values["trace_extension_counts"].append(extension_count)
                values["trace_extension_1_present"].append(1 if extension_1_present else 0)
                values["sample_counts"].append(ns)
                values["sample_intervals_us"].append(dt)

                if self._legacy_compact_header and self.trace_header_bytes == 38:
                    values["cdp"].append(self._i32(header, 0, endian))
                    values["offsets"].append(self._i32(header, 4, endian))
                    values["source_x_raw"].append(self._i32(header, 8, endian))
                    values["source_y_raw"].append(self._i32(header, 12, endian))
                    values["receiver_x_raw"].append(self._i32(header, 16, endian))
                    values["receiver_y_raw"].append(self._i32(header, 20, endian))
                    values["trace_sequence_line"].append(self._i32(header, 24, endian))
                    values["trace_sequence_file"].append(self._i32(header, 28, endian))
                    values["total_static_ms"].append(self._i16(header, 32, endian))
                    values["source_static_ms"].append(self._i16(header, 34, endian))
                    values["coordinate_units"].append(self._i16(header, 36, endian))
                    for key in (
                        "field_record", "trace_number", "energy_source_point", "cdp_trace",
                        "trace_identification", "elevation_scalar", "coordinate_scalar",
                        "receiver_static_ms", "delay_time_ms", "year", "day_of_year",
                        "hour", "minute", "second", "cdp_x_raw", "cdp_y_raw", "inline_3d",
                        "crossline_3d", "shotpoint",
                    ):
                        values[key].append(0)
                    for key in (
                        "source_x_ext", "source_y_ext", "receiver_x_ext", "receiver_y_ext",
                        "cdp_x_ext", "cdp_y_ext",
                    ):
                        values[key].append(float("nan"))
                else:
                    trace_sequence_line = self._i32(header, 0, endian)
                    trace_sequence_file = self._i32(header, 4, endian)
                    field_record = self._i32(header, 8, endian)
                    cdp = self._i32(header, 20, endian)
                    offset = self._i32(header, 36, endian)
                    sx_ext = sy_ext = gx_ext = gy_ext = cdp_x_ext = cdp_y_ext = float("nan")
                    if extension_1 is not None:
                        ext_value = self._u64(extension_1, 0, endian)
                        if ext_value:
                            trace_sequence_line = int(ext_value)
                        ext_value = self._u64(extension_1, 8, endian)
                        if ext_value:
                            trace_sequence_file = int(ext_value)
                        ext_value_i = self._i64(extension_1, 16, endian)
                        if ext_value_i:
                            field_record = int(ext_value_i)
                        ext_value_i = self._i64(extension_1, 24, endian)
                        if ext_value_i:
                            cdp = int(ext_value_i)
                        sx_ext = self._f64(extension_1, 96, endian)
                        sy_ext = self._f64(extension_1, 104, endian)
                        gx_ext = self._f64(extension_1, 112, endian)
                        gy_ext = self._f64(extension_1, 120, endian)
                        offset_ext = self._f64(extension_1, 128, endian)
                        cdp_x_ext = self._f64(extension_1, 160, endian)
                        cdp_y_ext = self._f64(extension_1, 168, endian)
                        if math.isfinite(offset_ext):
                            offset = float(offset_ext)

                    values["trace_sequence_line"].append(trace_sequence_line)
                    values["trace_sequence_file"].append(trace_sequence_file)
                    values["field_record"].append(field_record)
                    values["trace_number"].append(self._i32(header, 12, endian))
                    values["energy_source_point"].append(self._i32(header, 16, endian))
                    values["cdp"].append(cdp)
                    values["cdp_trace"].append(self._i32(header, 24, endian))
                    values["trace_identification"].append(self._i16(header, 28, endian))
                    values["offsets"].append(offset)
                    values["elevation_scalar"].append(self._i16(header, 68, endian))
                    values["coordinate_scalar"].append(self._i16(header, 70, endian))
                    values["source_x_raw"].append(self._i32(header, 72, endian))
                    values["source_y_raw"].append(self._i32(header, 76, endian))
                    values["receiver_x_raw"].append(self._i32(header, 80, endian))
                    values["receiver_y_raw"].append(self._i32(header, 84, endian))
                    values["source_x_ext"].append(sx_ext if math.isfinite(sx_ext) else float("nan"))
                    values["source_y_ext"].append(sy_ext if math.isfinite(sy_ext) else float("nan"))
                    values["receiver_x_ext"].append(gx_ext if math.isfinite(gx_ext) else float("nan"))
                    values["receiver_y_ext"].append(gy_ext if math.isfinite(gy_ext) else float("nan"))
                    values["coordinate_units"].append(self._i16(header, 88, endian))
                    values["source_static_ms"].append(self._i16(header, 98, endian))
                    values["receiver_static_ms"].append(self._i16(header, 100, endian))
                    values["total_static_ms"].append(self._i16(header, 102, endian))
                    values["delay_time_ms"].append(self._i16(header, 108, endian))
                    values["year"].append(self._u16(header, 156, endian))
                    values["day_of_year"].append(self._u16(header, 158, endian))
                    values["hour"].append(self._u16(header, 160, endian))
                    values["minute"].append(self._u16(header, 162, endian))
                    values["second"].append(self._u16(header, 164, endian))
                    values["cdp_x_raw"].append(self._i32(header, 180, endian))
                    values["cdp_y_raw"].append(self._i32(header, 184, endian))
                    values["cdp_x_ext"].append(cdp_x_ext if math.isfinite(cdp_x_ext) else float("nan"))
                    values["cdp_y_ext"].append(cdp_y_ext if math.isfinite(cdp_y_ext) else float("nan"))
                    values["inline_3d"].append(self._i32(header, 188, endian))
                    values["crossline_3d"].append(self._i32(header, 192, endian))
                    values["shotpoint"].append(self._i32(header, 196, endian))

                trace_number += 1
                position += trace_size
                if progress_callback and (trace_number == 1 or trace_number % 1000 == 0):
                    progress_callback(
                        min(1.0, (position - self.trace_data_start) / total_payload),
                        f"Indexed {trace_number:,} trace headers",
                    )

        arrays: Dict[str, np.ndarray] = {}
        float_keys = {
            "sample_intervals_us", "offsets",
            "source_x_ext", "source_y_ext", "receiver_x_ext", "receiver_y_ext",
            "cdp_x_ext", "cdp_y_ext",
        }
        int64_keys = {
            "byte_offsets", "header_sizes", "trace_sequence_line", "trace_sequence_file",
            "field_record", "cdp", "sample_counts",
        }
        for key, sequence in values.items():
            if key in float_keys:
                dtype = np.float64
            elif key in int64_keys:
                dtype = np.int64
            else:
                dtype = np.int32
            arrays[key] = np.asarray(sequence, dtype=dtype)

        source_x_scaled = self._apply_scalar(arrays["source_x_raw"], arrays["coordinate_scalar"])
        source_y_scaled = self._apply_scalar(arrays["source_y_raw"], arrays["coordinate_scalar"])
        receiver_x_scaled = self._apply_scalar(arrays["receiver_x_raw"], arrays["coordinate_scalar"])
        receiver_y_scaled = self._apply_scalar(arrays["receiver_y_raw"], arrays["coordinate_scalar"])
        cdp_x_scaled = self._apply_scalar(arrays["cdp_x_raw"], arrays["coordinate_scalar"])
        cdp_y_scaled = self._apply_scalar(arrays["cdp_y_raw"], arrays["coordinate_scalar"])
        source_x = np.where(np.isfinite(arrays["source_x_ext"]), arrays["source_x_ext"], source_x_scaled)
        source_y = np.where(np.isfinite(arrays["source_y_ext"]), arrays["source_y_ext"], source_y_scaled)
        receiver_x = np.where(np.isfinite(arrays["receiver_x_ext"]), arrays["receiver_x_ext"], receiver_x_scaled)
        receiver_y = np.where(np.isfinite(arrays["receiver_y_ext"]), arrays["receiver_y_ext"], receiver_y_scaled)
        cdp_x = np.where(np.isfinite(arrays["cdp_x_ext"]), arrays["cdp_x_ext"], cdp_x_scaled)
        cdp_y = np.where(np.isfinite(arrays["cdp_y_ext"]), arrays["cdp_y_ext"], cdp_y_scaled)

        self._trace_index = SegyTraceIndex(
            byte_offsets=arrays["byte_offsets"],
            header_sizes=arrays["header_sizes"],
            trace_extension_counts=arrays["trace_extension_counts"],
            trace_extension_1_present=arrays["trace_extension_1_present"].astype(bool),
            sample_counts=arrays["sample_counts"],
            sample_intervals_us=arrays["sample_intervals_us"],
            trace_sequence_line=arrays["trace_sequence_line"],
            trace_sequence_file=arrays["trace_sequence_file"],
            field_record=arrays["field_record"],
            trace_number=arrays["trace_number"],
            energy_source_point=arrays["energy_source_point"],
            cdp=arrays["cdp"],
            cdp_trace=arrays["cdp_trace"],
            trace_identification=arrays["trace_identification"],
            offsets=arrays["offsets"],
            elevation_scalar=arrays["elevation_scalar"],
            coordinate_scalar=arrays["coordinate_scalar"],
            source_x_raw=arrays["source_x_raw"],
            source_y_raw=arrays["source_y_raw"],
            receiver_x_raw=arrays["receiver_x_raw"],
            receiver_y_raw=arrays["receiver_y_raw"],
            source_x=source_x,
            source_y=source_y,
            receiver_x=receiver_x,
            receiver_y=receiver_y,
            coordinate_units=arrays["coordinate_units"],
            source_static_ms=arrays["source_static_ms"],
            receiver_static_ms=arrays["receiver_static_ms"],
            total_static_ms=arrays["total_static_ms"],
            delay_time_ms=arrays["delay_time_ms"],
            year=arrays["year"],
            day_of_year=arrays["day_of_year"],
            hour=arrays["hour"],
            minute=arrays["minute"],
            second=arrays["second"],
            cdp_x_raw=arrays["cdp_x_raw"],
            cdp_y_raw=arrays["cdp_y_raw"],
            cdp_x=cdp_x,
            cdp_y=cdp_y,
            inline_3d=arrays["inline_3d"],
            crossline_3d=arrays["crossline_3d"],
            shotpoint=arrays["shotpoint"],
            trace_end_offset=position,
            trailing_bytes=max(0, self.file_size - position),
            truncated=truncated,
        )
        if progress_callback:
            progress_callback(1.0, f"Indexed {self._trace_index.trace_count:,} trace headers")
        return self._trace_index

    @staticmethod
    def _decode_ibm32(raw: bytes, endian: str) -> np.ndarray:
        dtype = ">u4" if endian == ">" else "<u4"
        words = np.frombuffer(raw, dtype=dtype).astype(np.uint32, copy=False)
        sign = np.where((words & 0x80000000) != 0, -1.0, 1.0)
        exponent = ((words >> 24) & 0x7F).astype(np.int16) - 64
        fraction = (words & 0x00FFFFFF).astype(np.float64) / float(0x01000000)
        result = sign * fraction * np.power(16.0, exponent.astype(np.float64))
        result[words == 0] = 0.0
        return result.astype(np.float32)

    @staticmethod
    def _decode_int24(raw: bytes, endian: str, signed: bool) -> np.ndarray:
        data = np.frombuffer(raw, dtype=np.uint8)
        if data.size % 3:
            raise ValueError("Invalid 24-bit sample payload length")
        triplets = data.reshape(-1, 3).astype(np.uint32)
        if endian == ">":
            values = (triplets[:, 0] << 16) | (triplets[:, 1] << 8) | triplets[:, 2]
        else:
            values = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
        if signed:
            signed_values = values.astype(np.int32)
            negative = (values & 0x00800000) != 0
            signed_values[negative] -= 0x01000000
            return signed_values.astype(np.float32)
        return values.astype(np.float32)

    def decode_samples(self, raw: bytes) -> np.ndarray:
        code = self.binary_header.sample_format_code
        endian = self.binary_header.endian
        prefix = ">" if endian == ">" else "<"
        if code == 1:
            return self._decode_ibm32(raw, endian)
        if code == 2:
            return np.frombuffer(raw, dtype=f"{prefix}i4").astype(np.float32)
        if code == 3:
            return np.frombuffer(raw, dtype=f"{prefix}i2").astype(np.float32)
        if code == 5:
            dtype = "<f4" if self._legacy_compact_header else f"{prefix}f4"
            return np.frombuffer(raw, dtype=dtype).astype(np.float32, copy=False)
        if code == 6:
            return np.frombuffer(raw, dtype=f"{prefix}f8").astype(np.float64, copy=False)
        if code == 7:
            return self._decode_int24(raw, endian, signed=True)
        if code == 8:
            return np.frombuffer(raw, dtype=np.int8).astype(np.float32)
        if code == 9:
            return np.frombuffer(raw, dtype=f"{prefix}i8").astype(np.float64)
        if code == 10:
            return np.frombuffer(raw, dtype=f"{prefix}u4").astype(np.float64)
        if code == 11:
            return np.frombuffer(raw, dtype=f"{prefix}u2").astype(np.float32)
        if code == 12:
            return np.frombuffer(raw, dtype=f"{prefix}u8").astype(np.float64)
        if code == 15:
            return self._decode_int24(raw, endian, signed=False)
        if code == 16:
            return np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        raise ValueError(f"Unsupported SEG-Y sample format code: {code}")

    def read_trace_header(
        self, trace_index: int, index: Optional[SegyTraceIndex] = None
    ) -> SegyTraceHeader:
        trace_headers = index or self.scan_trace_headers()
        if trace_index < 0 or trace_index >= trace_headers.trace_count:
            raise IndexError(f"Trace index out of range: {trace_index}")
        return SegyTraceHeader(
            trace_sequence_line=int(trace_headers.trace_sequence_line[trace_index]),
            trace_sequence_file=int(trace_headers.trace_sequence_file[trace_index]),
            field_record=int(trace_headers.field_record[trace_index]),
            trace_number=int(trace_headers.trace_number[trace_index]),
            energy_source_point=int(trace_headers.energy_source_point[trace_index]),
            cdp=int(trace_headers.cdp[trace_index]),
            cdp_trace=int(trace_headers.cdp_trace[trace_index]),
            trace_identification=int(trace_headers.trace_identification[trace_index]),
            offset=float(trace_headers.offsets[trace_index]),
            elevation_scalar=int(trace_headers.elevation_scalar[trace_index]),
            coordinate_scalar=int(trace_headers.coordinate_scalar[trace_index]),
            source_x=float(trace_headers.source_x[trace_index]),
            source_y=float(trace_headers.source_y[trace_index]),
            receiver_x=float(trace_headers.receiver_x[trace_index]),
            receiver_y=float(trace_headers.receiver_y[trace_index]),
            coordinate_units=int(trace_headers.coordinate_units[trace_index]),
            source_static_ms=int(trace_headers.source_static_ms[trace_index]),
            receiver_static_ms=int(trace_headers.receiver_static_ms[trace_index]),
            total_static_ms=int(trace_headers.total_static_ms[trace_index]),
            delay_time_ms=int(trace_headers.delay_time_ms[trace_index]),
            sample_count=int(trace_headers.sample_counts[trace_index]),
            sample_interval_us=float(trace_headers.sample_intervals_us[trace_index]),
            year=int(trace_headers.year[trace_index]),
            day_of_year=int(trace_headers.day_of_year[trace_index]),
            hour=int(trace_headers.hour[trace_index]),
            minute=int(trace_headers.minute[trace_index]),
            second=int(trace_headers.second[trace_index]),
            cdp_x=float(trace_headers.cdp_x[trace_index]),
            cdp_y=float(trace_headers.cdp_y[trace_index]),
            inline_3d=int(trace_headers.inline_3d[trace_index]),
            crossline_3d=int(trace_headers.crossline_3d[trace_index]),
            shotpoint=int(trace_headers.shotpoint[trace_index]),
        )

    def read_trace(self, trace_index: int, index: Optional[SegyTraceIndex] = None) -> np.ndarray:
        trace_headers = index or self.scan_trace_headers()
        if trace_index < 0 or trace_index >= trace_headers.trace_count:
            raise IndexError(f"Trace index out of range: {trace_index}")
        byte_offset = int(trace_headers.byte_offsets[trace_index]) + int(trace_headers.header_sizes[trace_index])
        sample_count = int(trace_headers.sample_counts[trace_index])
        payload_bytes = sample_count * self.bytes_per_sample
        with self.file_path.open("rb") as handle:
            handle.seek(byte_offset)
            raw = handle.read(payload_bytes)
        if len(raw) != payload_bytes:
            raise ValueError(f"Trace {trace_index + 1} is truncated")
        return self.decode_samples(raw)

    def iter_traces(
        self,
        index: Optional[SegyTraceIndex] = None,
        trace_indices: Optional[Sequence[int]] = None,
        progress_callback: ProgressCallback = None,
        cancel_check: CancelCheck = None,
    ) -> Iterator[Tuple[int, np.ndarray]]:
        trace_headers = index or self.scan_trace_headers()
        indices: Sequence[int] = trace_indices if trace_indices is not None else range(trace_headers.trace_count)
        total = len(indices)
        with self.file_path.open("rb", buffering=4 * 1024 * 1024) as handle:
            for ordinal, trace_idx in enumerate(indices):
                if cancel_check and cancel_check():
                    raise InterruptedError("SEG-Y trace scan cancelled")
                byte_offset = int(trace_headers.byte_offsets[trace_idx]) + int(trace_headers.header_sizes[trace_idx])
                sample_count = int(trace_headers.sample_counts[trace_idx])
                payload_bytes = sample_count * self.bytes_per_sample
                handle.seek(byte_offset)
                raw = handle.read(payload_bytes)
                if len(raw) != payload_bytes:
                    raise ValueError(f"Trace {trace_idx + 1} is truncated")
                yield int(trace_idx), self.decode_samples(raw)
                if progress_callback and (ordinal == 0 or (ordinal + 1) % 100 == 0 or ordinal + 1 == total):
                    progress_callback(
                        (ordinal + 1) / max(1, total),
                        f"Analysed {ordinal + 1:,} of {total:,} traces",
                    )

    def get_trace_count(self) -> int:
        """Return the number of complete indexed traces (legacy API compatibility)."""
        return self.scan_trace_headers().trace_count

    def get_sample_count(self) -> int:
        """Return nominal samples per trace, falling back to indexed trace maxima."""
        nominal = int(self.binary_header.samples_per_trace)
        if nominal > 0:
            return nominal
        index = self.scan_trace_headers()
        return int(index.sample_counts.max()) if index.sample_counts.size else 0

    @staticmethod
    def _normalize_half_open_range(value: Tuple[int, int] | Sequence[int], limit: int, name: str) -> Tuple[int, int]:
        if value is None or len(value) != 2:
            raise ValueError(f"{name} must be a (start, end) pair")
        start, end = int(value[0]), int(value[1])
        if start < 0 or end < start:
            raise ValueError(f"Invalid {name}: ({start}, {end})")
        return min(start, limit), min(end, limit)

    def read_trace_headers(
        self, trace_range: Tuple[int, int] | Sequence[int] | None = None
    ) -> np.ndarray:
        """Return trace headers as a structured NumPy array.

        This compatibility facade is backed by the current streaming trace index;
        it does not re-read trace samples or memory-map the entire SEG-Y file.
        Common historical field aliases are included so older QC stages and saved
        workflows continue to operate.
        """
        index = self.scan_trace_headers()
        if trace_range is None:
            start, end = 0, index.trace_count
        else:
            start, end = self._normalize_half_open_range(trace_range, index.trace_count, "trace_range")
        size = max(0, end - start)
        dtype = np.dtype([
            ("trace_sequence_line", "<i8"), ("trace_sequence_file", "<i8"),
            ("field_record", "<i8"), ("trace_number", "<i4"),
            ("energy_source_point", "<i4"), ("cdp", "<i8"), ("cdp_trace", "<i4"),
            ("trace_identification", "<i4"), ("offset", "<f8"),
            ("elevation_scalar", "<i4"), ("coordinate_scalar", "<i4"),
            ("source_x", "<f8"), ("source_y", "<f8"),
            ("receiver_x", "<f8"), ("receiver_y", "<f8"),
            ("receiver_group_x", "<f8"), ("receiver_group_y", "<f8"),
            ("coordinate_units", "<i4"),
            ("source_static_ms", "<i4"), ("receiver_static_ms", "<i4"),
            ("total_static_ms", "<i4"), ("total_static", "<i4"),
            ("source_to_receiver_static", "<i4"), ("delay_time_ms", "<i4"),
            ("sample_count", "<i8"), ("sample_interval_us", "<f8"),
            ("year", "<i4"), ("day_of_year", "<i4"), ("hour", "<i4"),
            ("minute", "<i4"), ("second", "<i4"),
            ("cdp_x", "<f8"), ("cdp_y", "<f8"), ("inline_3d", "<i4"),
            ("crossline_3d", "<i4"), ("shotpoint", "<i4"),
        ])
        result = np.zeros(size, dtype=dtype)
        if size == 0:
            return result
        sl = slice(start, end)
        mapping = {
            "trace_sequence_line": index.trace_sequence_line,
            "trace_sequence_file": index.trace_sequence_file, "field_record": index.field_record,
            "trace_number": index.trace_number, "energy_source_point": index.energy_source_point,
            "cdp": index.cdp, "cdp_trace": index.cdp_trace,
            "trace_identification": index.trace_identification, "offset": index.offsets,
            "elevation_scalar": index.elevation_scalar, "coordinate_scalar": index.coordinate_scalar,
            "source_x": index.source_x, "source_y": index.source_y,
            "receiver_x": index.receiver_x, "receiver_y": index.receiver_y,
            "receiver_group_x": index.receiver_x, "receiver_group_y": index.receiver_y,
            "coordinate_units": index.coordinate_units, "source_static_ms": index.source_static_ms,
            "receiver_static_ms": index.receiver_static_ms, "total_static_ms": index.total_static_ms,
            "total_static": index.total_static_ms, "source_to_receiver_static": index.source_static_ms,
            "delay_time_ms": index.delay_time_ms, "sample_count": index.sample_counts,
            "sample_interval_us": index.sample_intervals_us, "year": index.year,
            "day_of_year": index.day_of_year, "hour": index.hour, "minute": index.minute,
            "second": index.second, "cdp_x": index.cdp_x, "cdp_y": index.cdp_y,
            "inline_3d": index.inline_3d, "crossline_3d": index.crossline_3d,
            "shotpoint": index.shotpoint,
        }
        for field, source in mapping.items():
            result[field] = source[sl]
        return result

    def read_trace_window(
        self,
        trace_range: Tuple[int, int] | Sequence[int],
        sample_range: Tuple[int, int] | Sequence[int],
    ) -> np.ndarray:
        """Read a bounded 2-D trace/sample window without loading the whole file."""
        index = self.scan_trace_headers()
        trace_start, trace_end = self._normalize_half_open_range(
            trace_range, index.trace_count, "trace_range"
        )
        sample_start, sample_end = int(sample_range[0]), int(sample_range[1])
        if sample_start < 0 or sample_end < sample_start:
            raise ValueError(f"Invalid sample_range: ({sample_start}, {sample_end})")
        width = sample_end - sample_start
        result = np.zeros((trace_end - trace_start, width), dtype=np.float32)
        if result.size == 0:
            return result

        with self.file_path.open("rb", buffering=4 * 1024 * 1024) as handle:
            for row, trace_idx in enumerate(range(trace_start, trace_end)):
                available = int(index.sample_counts[trace_idx])
                if sample_start >= available:
                    continue
                count = max(0, min(sample_end, available) - sample_start)
                if count <= 0:
                    continue
                payload_offset = (int(index.byte_offsets[trace_idx]) + int(index.header_sizes[trace_idx])
                                  + sample_start * self.bytes_per_sample)
                handle.seek(payload_offset)
                raw = handle.read(count * self.bytes_per_sample)
                if len(raw) != count * self.bytes_per_sample:
                    raise ValueError(f"Trace {trace_idx + 1} is truncated")
                samples = self.decode_samples(raw)
                result[row, :count] = np.asarray(samples, dtype=np.float32)
        return result

    def expected_fixed_file_size(self, trace_count: int) -> int:
        return self.trace_data_start + trace_count * (
            self.trace_header_bytes
            + self.binary_header.samples_per_trace * self.bytes_per_sample
        )