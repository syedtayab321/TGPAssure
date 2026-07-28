from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    from core.data_access.local_file_cache import FileCacheManager, LocalActivityHistory
except Exception:  # pragma: no cover - cache is an optional startup accelerator
    FileCacheManager = None  # type: ignore[assignment]
    LocalActivityHistory = None  # type: ignore[assignment]


@dataclass
class SegdGeneralHeader1:
    file_number: int
    general_header_length: int
    channel_set_descriptor_length: int
    extended_header_length: int
    standard_headers_length: int
    channel_set_count: int
    trace_count_per_channel_set: int
    manufacturer_code: int
    version: int
    format_code: int
    time_base: int
    flags: int
    date: str
    time: str


@dataclass
class SegdGeneralHeader2:
    maximum_traces: int
    channel_sets_count: int
    year: int
    day: int
    hour: int
    minute: int
    second: int
    ms: int
    flags: int


@dataclass
class SegdGeneralHeader3:
    expansion_length: int
    flags: int
    channel_set_descriptor_length: int
    standard_headers_length: int
    extended_headers_count: int


@dataclass
class SegdChannelSetDescriptor:
    channel_set_id: int
    channel_count: int
    sample_count: int
    sample_format: int
    sample_interval: float
    scan_type: int
    channel_type: int
    gain_type: int
    alias_filter: int
    aux_1_count: int
    aux_2_count: int
    aux_3_count: int
    calibration_data: int
    unit_of_measurement: int
    offset: int
    data_type: int
    trace_length: int
    flags: int
    trace_header_extensions: int = 0
    start_time_ms: float = 0.0
    end_time_ms: float = 0.0


@dataclass
class SegdTraceInfo:
    physical_index: int
    header_offset: int
    data_offset: int
    file_number: int
    scan_type: int
    channel_set: int
    trace_number: int
    trace_header_extensions: int
    trace_edit: int
    extended_channel_set: int
    extended_file_number: int
    receiver_line: float
    receiver_point: float
    receiver_index: int
    sensor_type: int
    sample_count: int
    sample_interval_ms: float
    channel_type: int
    receiver_x: Optional[float] = None
    receiver_y: Optional[float] = None
    receiver_elevation: Optional[float] = None
    resistance: Optional[float] = None
    resistance_low_limit: Optional[float] = None
    resistance_high_limit: Optional[float] = None
    capacitance: Optional[float] = None
    capacitance_low_limit: Optional[float] = None
    capacitance_high_limit: Optional[float] = None
    leakage: Optional[float] = None
    leakage_limit: Optional[float] = None
    tilt: Optional[float] = None
    tilt_limit: Optional[float] = None
    instrument_longitude: Optional[float] = None
    instrument_latitude: Optional[float] = None
    instrument_elevation: Optional[float] = None
    qc_flags: Tuple[str, ...] = ()
    extensions_decoded: bool = False


class SegdReader:
    SUPPORTED_FORMAT_CODE = 8058
    TRACE_HEADER_SIZE = 20
    TRACE_EXTENSION_SIZE = 32
    SAMPLE_SIZE = 4

    def __init__(
        self,
        file_path: str | Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        self.file_path = Path(file_path)
        self._progress_callback = progress_callback
        if not self.file_path.is_file():
            raise FileNotFoundError(f"SEG-D file not found: {self.file_path}")

        self.file_size = self.file_path.stat().st_size
        if self.file_size < 64:
            raise ValueError("The selected file is too small to contain a valid SEG-D record.")

        self._memmap = np.memmap(self.file_path, dtype=np.uint8, mode="r")
        self._legacy_compact = self._looks_like_legacy_compact()
        self._sample_endian = ">"
        if self._legacy_compact:
            self._initialize_legacy_compact()
            self._record_local_history("open_index", {"format": "legacy_compact", "cache_hit": False})
            return
        cached = self._try_restore_index_cache()
        if cached:
            self._report_progress(100, "SEG-D index loaded from local cache")
            self._record_local_history("open_index", {"format": self.get_format_code(), "cache_hit": True, "traces": self.get_trace_count()})
            return
        self._record_start_offset = self._detect_record_start_offset()
        self._gh1_raw = self._read_bytes(self._record_start_offset, 32)
        self._gh1 = self._parse_general_header_block_1(self._gh1_raw)

        if self._gh1["format_code"] != self.SUPPORTED_FORMAT_CODE:
            raise ValueError(
                f"Unsupported SEG-D format code {self._gh1['format_code']}. "
                f"This reader currently supports format 8058 only."
            )

        self._additional_general_blocks = self._gh1["additional_general_blocks"]
        if self._additional_general_blocks < 1:
            self._additional_general_blocks = 1

        self._gh2_raw = self._read_bytes(self._record_start_offset + 32, 32)
        self._gh2 = self._parse_general_header_block_2(self._gh2_raw)
        self._revision_major = self._gh2["revision_major"]
        self._revision_minor = self._gh2["revision_minor"]

        self._general_header_block_count = 1 + self._additional_general_blocks
        self._general_header_bytes = self._general_header_block_count * 32
        self._scan_type_count = self._resolve_scan_type_count()
        self._channel_sets_per_scan_type = self._resolve_channel_set_count()
        self._skew_blocks_per_scan_type = self._gh1["skew_blocks"]
        self._extended_header_blocks = self._resolve_extended_header_blocks()
        self._external_header_blocks = self._resolve_external_header_blocks()
        self._general_trailer_blocks = self._gh2["general_trailer_blocks"]
        self._base_scan_interval_ms = self._gh1["base_scan_interval_ms"]

        self.general_header_1 = self._build_general_header_1()
        self.general_header_2 = self._build_general_header_2()
        self.general_header_3 = self._build_general_header_3()

        self.channel_set_descriptors = self._parse_channel_set_descriptors()
        if not self.channel_set_descriptors:
            raise ValueError("No valid SEG-D channel-set descriptors were found.")

        self._data_start_offset = self._calculate_data_start_offset()
        if self._data_start_offset >= self.file_size:
            raise ValueError("SEG-D header lengths place the trace data beyond the end of the file.")

        self._report_progress(12, "Indexing SEG-D traces")
        self._trace_index = self._build_trace_index()
        if not self._trace_index:
            raise ValueError("No valid SEG-D traces could be indexed from this file.")

        self._trace_count = len(self._trace_index)
        self._seismic_trace_count = sum(1 for trace in self._trace_index if trace.channel_type == 1)
        self._aux_trace_count = self._trace_count - self._seismic_trace_count
        self._sample_count = max(trace.sample_count for trace in self._trace_index)
        self._channel_count = 1
        self._sample_interval = self._resolve_primary_sample_interval()
        self._sample_format = self.SUPPORTED_FORMAT_CODE
        self._sample_size = self.SAMPLE_SIZE
        self._trace_headers_size = self.TRACE_HEADER_SIZE
        self._header_size = self._general_header_bytes
        self._channel_set_descriptor_size = 32
        self._extended_header_size = self._extended_header_blocks * 32
        self._trace_size = 0
        self._save_index_cache()
        self._record_local_history("open_index", {"format": self.get_format_code(), "cache_hit": False, "traces": self.get_trace_count()})
        self._report_progress(100, "SEG-D file indexed")

    def _cache_payload_fields(self) -> tuple[str, ...]:
        return (
            "_record_start_offset", "_gh1_raw", "_gh1", "_gh2_raw", "_gh2",
            "_additional_general_blocks", "_revision_major", "_revision_minor",
            "_general_header_block_count", "_general_header_bytes", "_scan_type_count",
            "_channel_sets_per_scan_type", "_skew_blocks_per_scan_type",
            "_extended_header_blocks", "_external_header_blocks", "_general_trailer_blocks",
            "_base_scan_interval_ms", "general_header_1", "general_header_2",
            "general_header_3", "channel_set_descriptors", "_data_start_offset",
            "_trace_index", "_trace_count", "_seismic_trace_count", "_aux_trace_count",
            "_sample_count", "_channel_count", "_sample_interval", "_sample_format",
            "_sample_size", "_trace_headers_size", "_header_size",
            "_channel_set_descriptor_size", "_extended_header_size", "_trace_size",
            "_sample_endian",
        )

    def _try_restore_index_cache(self) -> bool:
        if FileCacheManager is None:
            return False
        try:
            cache = FileCacheManager()
            payload, status = cache.load(
                "segd_trace_index",
                self.file_path,
                schema_version="segd_trace_index_v2",
            )
            if not status.hit or not isinstance(payload, dict):
                return False
            for key, value in payload.items():
                setattr(self, key, value)
            return bool(getattr(self, "_trace_index", None))
        except Exception:
            return False

    def _save_index_cache(self) -> None:
        if FileCacheManager is None:
            return
        try:
            payload = {key: getattr(self, key) for key in self._cache_payload_fields() if hasattr(self, key)}
            FileCacheManager().store(
                "segd_trace_index",
                self.file_path,
                payload,
                schema_version="segd_trace_index_v2",
            )
        except Exception:
            return

    def _record_local_history(self, action: str, details: dict[str, Any]) -> None:
        if LocalActivityHistory is None:
            return
        try:
            LocalActivityHistory().record(
                module="segd",
                action=action,
                file_path=self.file_path,
                details=details,
            )
        except Exception:
            return

    def _looks_like_legacy_compact(self) -> bool:
        """Detect the early TGPAssure compact SEG-D project layout.

        This compatibility format predates the current standards-aware 8058
        reader. Detection is intentionally strict so genuine SEG-D records always
        take the normal parser path.
        """
        if self.file_size < 64 * 3 + 32:
            return False
        block = self._read_bytes(0, 64)
        if len(block) != 64:
            return False
        try:
            general_length = int.from_bytes(block[2:4], "big", signed=True)
            descriptor_length = int.from_bytes(block[4:6], "big", signed=True)
            standard_headers = int.from_bytes(block[8:10], "big", signed=True)
            channel_sets = int.from_bytes(block[10:12], "big", signed=True)
            trace_count = int.from_bytes(block[12:14], "big", signed=True)
            sample_format = int.from_bytes(block[18:20], "big", signed=True)
        except Exception:
            return False
        return (
            general_length == 64
            and descriptor_length == 32
            and standard_headers in (0, 240)
            and 1 <= channel_sets <= 128
            and 1 <= trace_count <= 10_000_000
            and sample_format in (4, 5)
        )

    @staticmethod
    def _legacy_i16(block: bytes, offset: int) -> int:
        return int.from_bytes(block[offset:offset + 2], "big", signed=True)

    def _initialize_legacy_compact(self) -> None:
        """Initialize read-only compatibility for pre-8058 TGPAssure files."""
        gh1 = self._read_bytes(0, 64)
        gh2 = self._read_bytes(64, 64)
        gh3 = self._read_bytes(128, 64)
        descriptor_raw = self._read_bytes(192, 32)
        if min(map(len, (gh1, gh2, gh3, descriptor_raw))) == 0:
            raise ValueError("Legacy SEG-D compatibility headers are incomplete")

        file_number = self._legacy_i16(gh1, 0)
        general_length = max(64, self._legacy_i16(gh1, 2))
        descriptor_length = max(32, self._legacy_i16(gh1, 4))
        extended_length = max(0, self._legacy_i16(gh1, 6))
        standard_headers = max(0, self._legacy_i16(gh1, 8))
        channel_set_count = max(1, self._legacy_i16(gh1, 10))
        trace_count = max(0, self._legacy_i16(gh1, 12))
        manufacturer = self._legacy_i16(gh1, 14)
        version = self._legacy_i16(gh1, 16)
        format_code = self._legacy_i16(gh1, 18)
        time_base = self._legacy_i16(gh1, 20)

        maximum_traces = max(trace_count, self._legacy_i16(gh2, 0))
        year = self._legacy_i16(gh2, 4)
        day = self._legacy_i16(gh2, 6)
        hour = self._legacy_i16(gh2, 8)
        minute = self._legacy_i16(gh2, 10)
        second = self._legacy_i16(gh2, 12)
        milliseconds = self._legacy_i16(gh2, 14)

        channel_set_id = max(1, self._legacy_i16(descriptor_raw, 0))
        descriptor_channel_count = max(0, self._legacy_i16(descriptor_raw, 2))
        sample_count = max(0, self._legacy_i16(descriptor_raw, 4))
        sample_format = self._legacy_i16(descriptor_raw, 6)
        sample_interval_ms = float(max(0, self._legacy_i16(descriptor_raw, 8)))
        if sample_count <= 0 or trace_count <= 0:
            raise ValueError("Legacy SEG-D file reports no usable traces or samples")
        if sample_format not in (4, 5):
            raise ValueError(f"Unsupported legacy SEG-D sample format: {sample_format}")

        data_start = 64 * 3 + descriptor_length * channel_set_count + standard_headers + extended_length
        required = data_start + trace_count * sample_count * self.SAMPLE_SIZE
        if required > self.file_size:
            raise ValueError("Legacy SEG-D trace payload is truncated")

        self._record_start_offset = 0
        self._general_header_block_count = 2
        self._general_header_bytes = general_length
        self._scan_type_count = 1
        self._channel_sets_per_scan_type = channel_set_count
        self._skew_blocks_per_scan_type = 0
        self._extended_header_blocks = 0
        self._external_header_blocks = 0
        self._general_trailer_blocks = 0
        self._base_scan_interval_ms = sample_interval_ms
        self._revision_major = max(0, version)
        self._revision_minor = 0
        self._sample_endian = "<"  # historical files stored native little-endian float32
        self._gh1 = {"format_code": format_code}
        self._gh2 = {}

        self.general_header_1 = SegdGeneralHeader1(
            file_number=file_number, general_header_length=general_length,
            channel_set_descriptor_length=descriptor_length, extended_header_length=extended_length,
            standard_headers_length=standard_headers, channel_set_count=channel_set_count,
            trace_count_per_channel_set=trace_count, manufacturer_code=manufacturer,
            version=version, format_code=format_code, time_base=time_base, flags=0,
            date=f"{year:04d}-DOY{day:03d}", time=f"{hour:02d}:{minute:02d}:{second:02d}",
        )
        self.general_header_2 = SegdGeneralHeader2(
            maximum_traces=maximum_traces, channel_sets_count=max(1, self._legacy_i16(gh2, 2)),
            year=year, day=day, hour=hour, minute=minute, second=second, ms=milliseconds, flags=0,
        )
        self.general_header_3 = SegdGeneralHeader3(
            expansion_length=max(0, self._legacy_i16(gh3, 0)),
            flags=self._legacy_i16(gh3, 2),
            channel_set_descriptor_length=max(32, self._legacy_i16(gh3, 4)),
            standard_headers_length=max(0, self._legacy_i16(gh3, 6)),
            extended_headers_count=max(0, self._legacy_i16(gh3, 8)),
        )
        self.channel_set_descriptors = [SegdChannelSetDescriptor(
            channel_set_id=channel_set_id, channel_count=descriptor_channel_count,
            sample_count=sample_count, sample_format=sample_format, sample_interval=sample_interval_ms,
            scan_type=1, channel_type=1, gain_type=0, alias_filter=0, aux_1_count=0, aux_2_count=0,
            aux_3_count=0, calibration_data=0, unit_of_measurement=0, offset=192, data_type=1,
            trace_length=int(round(max(0, sample_count - 1) * sample_interval_ms)), flags=0,
            trace_header_extensions=0, start_time_ms=0.0,
            end_time_ms=max(0.0, (sample_count - 1) * sample_interval_ms),
        )]
        self._data_start_offset = data_start
        self._trace_index = []
        for i in range(trace_count):
            data_offset = data_start + i * sample_count * self.SAMPLE_SIZE
            self._trace_index.append(SegdTraceInfo(
                physical_index=i, header_offset=data_start, data_offset=data_offset, file_number=file_number,
                scan_type=1, channel_set=channel_set_id, trace_number=i + 1, trace_header_extensions=0,
                trace_edit=0, extended_channel_set=0, extended_file_number=0, receiver_line=0,
                receiver_point=float(i + 1), receiver_index=i, sensor_type=1, sample_count=sample_count,
                sample_interval_ms=sample_interval_ms, channel_type=1, extensions_decoded=True,
            ))
        self._trace_count = trace_count
        self._seismic_trace_count = trace_count
        self._aux_trace_count = 0
        self._sample_count = sample_count
        self._channel_count = 1
        self._sample_interval = sample_interval_ms
        self._sample_format = sample_format
        self._sample_size = self.SAMPLE_SIZE
        self._trace_headers_size = standard_headers
        self._header_size = general_length
        self._channel_set_descriptor_size = descriptor_length
        self._extended_header_size = extended_length
        self._trace_size = sample_count * self.SAMPLE_SIZE
        self._report_progress(100, "Legacy SEG-D project file indexed")

    def _detect_record_start_offset(self) -> int:
        for offset in (0, 128):
            if offset + 32 > self.file_size:
                continue
            block = self._read_bytes(offset, 32)
            try:
                format_code = self._decode_bcd(block[2:4], allow_f=False)
            except ValueError:
                continue
            if format_code == self.SUPPORTED_FORMAT_CODE:
                return offset
        raise ValueError("The file does not contain a recognizable SEG-D 8058 general header at byte 0 or byte 128.")

    def _parse_general_header_block_1(self, block: bytes) -> Dict[str, Any]:
        if len(block) != 32:
            raise ValueError("General Header Block #1 is incomplete.")

        file_number = self._decode_bcd(block[0:2], allow_f=True)
        format_code = self._decode_bcd(block[2:4], allow_f=False)
        year_two_digits = self._decode_bcd(block[10:11], allow_f=False)
        additional_general_blocks = (block[11] >> 4) & 0x0F
        julian_hundreds = block[11] & 0x0F
        julian_tail = self._decode_bcd(block[12:13], allow_f=False)
        julian_day = julian_hundreds * 100 + julian_tail
        hour = self._decode_bcd(block[13:14], allow_f=False)
        minute = self._decode_bcd(block[14:15], allow_f=False)
        second = self._decode_bcd(block[15:16], allow_f=False)
        manufacturer_code = self._decode_bcd(block[16:17], allow_f=True)
        manufacturer_serial = self._decode_bcd(block[17:19], allow_f=True)
        base_scan_interval_ms = block[22] / 16.0
        record_type = (block[25] >> 4) & 0x0F
        scan_type_count = self._decode_bcd(block[27:28], allow_f=True)
        channel_sets = self._decode_bcd(block[28:29], allow_f=True)
        skew_blocks = self._decode_bcd(block[29:30], allow_f=True)
        extended_header_blocks = self._decode_bcd(block[30:31], allow_f=True)
        external_header_blocks = self._decode_bcd(block[31:32], allow_f=True)

        return {
            "file_number": file_number,
            "format_code": format_code,
            "year_two_digits": year_two_digits,
            "additional_general_blocks": additional_general_blocks,
            "julian_day": julian_day,
            "hour": hour,
            "minute": minute,
            "second": second,
            "manufacturer_code": manufacturer_code,
            "manufacturer_serial": manufacturer_serial,
            "base_scan_interval_ms": base_scan_interval_ms,
            "record_type": record_type,
            "scan_type_count": scan_type_count,
            "channel_sets": channel_sets,
            "skew_blocks": skew_blocks,
            "extended_header_blocks": extended_header_blocks,
            "external_header_blocks": external_header_blocks,
        }

    def _parse_general_header_block_2(self, block: bytes) -> Dict[str, Any]:
        if len(block) != 32:
            raise ValueError("General Header Block #2 is incomplete.")

        return {
            "expanded_file_number": self._decode_uint(block[0:3]),
            "extended_channel_sets": self._decode_uint(block[3:5]),
            "extended_header_blocks": self._decode_uint(block[5:7]),
            "external_header_blocks": self._decode_uint(block[7:9]),
            "revision_major": int(block[10]),
            "revision_minor": int(block[11]),
            "general_trailer_blocks": self._decode_uint(block[12:14]),
            "extended_record_length_ms": self._decode_uint(block[14:17]),
            "block_number": int(block[18]),
            "sequence_number": self._decode_uint(block[20:22]),
        }

    def _build_general_header_1(self) -> SegdGeneralHeader1:
        file_number = self._gh1["file_number"]
        if file_number < 0:
            file_number = self._gh2["expanded_file_number"]

        full_year = self._full_year(self._gh1["year_two_digits"])
        julian_day = self._gh1["julian_day"]
        date_text = self._format_julian_date(full_year, julian_day)
        time_text = f"{self._gh1['hour']:02d}:{self._gh1['minute']:02d}:{self._gh1['second']:02d}"
        revision = self._gh2["revision_major"] * 10 + self._gh2["revision_minor"]

        return SegdGeneralHeader1(
            file_number=file_number,
            general_header_length=self._general_header_bytes,
            channel_set_descriptor_length=32,
            extended_header_length=self._extended_header_blocks * 32,
            standard_headers_length=self.TRACE_HEADER_SIZE,
            channel_set_count=self._channel_sets_per_scan_type,
            trace_count_per_channel_set=0,
            manufacturer_code=self._gh1["manufacturer_code"],
            version=revision,
            format_code=self._gh1["format_code"],
            time_base=int(round(self._gh1["base_scan_interval_ms"] * 1000.0)),
            flags=self._gh1["record_type"],
            date=date_text,
            time=time_text,
        )

    def _build_general_header_2(self) -> SegdGeneralHeader2:
        full_year = self._full_year(self._gh1["year_two_digits"])
        return SegdGeneralHeader2(
            maximum_traces=0,
            channel_sets_count=self._channel_sets_per_scan_type,
            year=full_year,
            day=self._gh1["julian_day"],
            hour=self._gh1["hour"],
            minute=self._gh1["minute"],
            second=self._gh1["second"],
            ms=0,
            flags=self._gh2["sequence_number"],
        )

    def _build_general_header_3(self) -> SegdGeneralHeader3:
        return SegdGeneralHeader3(
            expansion_length=max(0, self._general_header_block_count - 2) * 32,
            flags=self._gh2["general_trailer_blocks"],
            channel_set_descriptor_length=32,
            standard_headers_length=self.TRACE_HEADER_SIZE,
            extended_headers_count=self._extended_header_blocks,
        )

    def _resolve_scan_type_count(self) -> int:
        value = self._gh1["scan_type_count"]
        if value <= 0 or value == 255:
            return 1
        return value

    def _resolve_channel_set_count(self) -> int:
        value = self._gh1["channel_sets"]
        if value == 255:
            value = self._gh2["extended_channel_sets"]
        if value <= 0:
            raise ValueError("SEG-D header reports zero channel sets.")
        return value

    def _resolve_extended_header_blocks(self) -> int:
        value = self._gh1["extended_header_blocks"]
        if value == 255:
            value = self._gh2["extended_header_blocks"]
        return max(0, value)

    def _resolve_external_header_blocks(self) -> int:
        value = self._gh1["external_header_blocks"]
        if value == 255:
            value = self._gh2["external_header_blocks"]
        return max(0, value)

    def _parse_channel_set_descriptors(self) -> List[SegdChannelSetDescriptor]:
        descriptors: List[SegdChannelSetDescriptor] = []
        scan_header_start = self._record_start_offset + self._general_header_bytes

        for scan_index in range(self._scan_type_count):
            scan_start = scan_header_start + scan_index * (
                self._channel_sets_per_scan_type * 32 + self._skew_blocks_per_scan_type * 32
            )
            for set_index in range(self._channel_sets_per_scan_type):
                offset = scan_start + set_index * 32
                block = self._read_bytes(offset, 32)
                if len(block) != 32:
                    raise ValueError("A channel-set descriptor is truncated.")

                scan_type = self._decode_bcd(block[0:1], allow_f=True)
                channel_set_id = self._decode_bcd(block[1:2], allow_f=True)
                extended_channel_set = self._decode_uint(block[26:28])
                if channel_set_id == 255 and extended_channel_set > 0:
                    channel_set_id = extended_channel_set
                if scan_type <= 0 or scan_type == 255:
                    scan_type = scan_index + 1
                if channel_set_id <= 0 or channel_set_id == 255:
                    channel_set_id = set_index + 1

                start_time_ms = self._decode_uint(block[2:4]) * 2.0
                end_time_ms = self._decode_uint(block[4:6]) * 2.0
                channel_count = self._decode_bcd(block[8:10], allow_f=True)
                if channel_count == 255:
                    channel_count = 0
                channel_type = (block[10] >> 4) & 0x0F
                subscan_exponent = (block[11] >> 4) & 0x0F
                gain_type = block[11] & 0x0F
                sample_interval_ms = self._base_scan_interval_ms / float(2 ** subscan_exponent)
                if sample_interval_ms <= 0:
                    sample_interval_ms = self._base_scan_interval_ms if self._base_scan_interval_ms > 0 else 2.0
                sample_count = self._calculate_descriptor_sample_count(start_time_ms, end_time_ms, sample_interval_ms)
                trace_header_extensions = block[28] & 0x0F
                trace_length_ms = max(0.0, end_time_ms - start_time_ms)
                alias_filter = self._decode_bcd(block[12:14], allow_f=True)

                descriptors.append(
                    SegdChannelSetDescriptor(
                        channel_set_id=channel_set_id,
                        channel_count=max(0, channel_count),
                        sample_count=max(0, sample_count),
                        sample_format=self.SUPPORTED_FORMAT_CODE,
                        sample_interval=sample_interval_ms,
                        scan_type=scan_type,
                        channel_type=channel_type,
                        gain_type=gain_type,
                        alias_filter=alias_filter,
                        aux_1_count=0,
                        aux_2_count=0,
                        aux_3_count=0,
                        calibration_data=0,
                        unit_of_measurement=0,
                        offset=offset,
                        data_type=channel_type,
                        trace_length=int(round(trace_length_ms)),
                        flags=int(block[28]),
                        trace_header_extensions=trace_header_extensions,
                        start_time_ms=start_time_ms,
                        end_time_ms=end_time_ms,
                    )
                )

        nonzero_counts = [item.channel_count for item in descriptors if item.channel_count > 0]
        if nonzero_counts:
            self.general_header_1.trace_count_per_channel_set = max(nonzero_counts)
            self.general_header_2.maximum_traces = sum(nonzero_counts)
        return descriptors

    def _calculate_data_start_offset(self) -> int:
        scan_type_header_bytes = self._scan_type_count * (
            self._channel_sets_per_scan_type * 32 + self._skew_blocks_per_scan_type * 32
        )
        return (
            self._record_start_offset
            + self._general_header_bytes
            + scan_type_header_bytes
            + self._extended_header_blocks * 32
            + self._external_header_blocks * 32
        )

    def _build_trace_index(self) -> List[SegdTraceInfo]:
        traces: List[SegdTraceInfo] = []
        offset = self._data_start_offset
        physical_index = 0
        expected_traces = max(1, sum(max(0, item.channel_count) for item in self.channel_set_descriptors))
        progress_step = max(1, expected_traces // 100)

        for descriptor in self.channel_set_descriptors:
            if descriptor.channel_count <= 0:
                continue

            for trace_in_set in range(descriptor.channel_count):
                if offset + self.TRACE_HEADER_SIZE > self.file_size:
                    return traces

                header = self._read_bytes(offset, self.TRACE_HEADER_SIZE)
                parsed = self._parse_trace_header(header)
                extension_count = parsed["trace_header_extensions"]
                if extension_count <= 0:
                    extension_count = descriptor.trace_header_extensions
                extension_count = max(0, min(15, extension_count))

                extension_bytes = extension_count * self.TRACE_EXTENSION_SIZE
                data_offset = offset + self.TRACE_HEADER_SIZE + extension_bytes
                if data_offset > self.file_size:
                    return traces

                receiver_line = 0
                receiver_point = 0
                receiver_index = 0
                sensor_type = 0
                extension_sample_count = 0

                if extension_count > 0 and offset + self.TRACE_HEADER_SIZE + self.TRACE_EXTENSION_SIZE <= self.file_size:
                    extension = self._read_bytes(offset + self.TRACE_HEADER_SIZE, self.TRACE_EXTENSION_SIZE)
                    receiver_line = self._decode_uint(extension[0:3])
                    receiver_point = self._decode_uint(extension[3:6])
                    receiver_index = int(extension[6])
                    if receiver_line == 0xFFFFFF:
                        receiver_line = 0
                    if receiver_point == 0xFFFFFF:
                        receiver_point = 0
                    extension_sample_count = self._decode_uint(extension[7:10])
                    sensor_type = int(extension[20])

                sample_count = extension_sample_count if extension_sample_count > 0 else descriptor.sample_count
                if sample_count <= 0:
                    sample_count = self._infer_sample_count_from_remaining(
                        data_offset,
                        descriptor,
                        descriptor.channel_count - trace_in_set,
                    )
                if sample_count <= 0:
                    return traces

                data_end = data_offset + sample_count * self.SAMPLE_SIZE
                if data_end > self.file_size:
                    inferred = self._infer_sample_count_from_remaining(
                        data_offset,
                        descriptor,
                        descriptor.channel_count - trace_in_set,
                    )
                    if inferred <= 0:
                        return traces
                    sample_count = inferred
                    data_end = data_offset + sample_count * self.SAMPLE_SIZE
                    if data_end > self.file_size:
                        return traces

                channel_set = parsed["channel_set"]
                if channel_set <= 0:
                    channel_set = descriptor.channel_set_id
                scan_type = parsed["scan_type"]
                if scan_type <= 0:
                    scan_type = descriptor.scan_type
                trace_number = parsed["trace_number"]
                if trace_number <= 0:
                    trace_number = trace_in_set + 1

                traces.append(
                    SegdTraceInfo(
                        physical_index=physical_index,
                        header_offset=offset,
                        data_offset=data_offset,
                        file_number=parsed["file_number"],
                        scan_type=scan_type,
                        channel_set=channel_set,
                        trace_number=trace_number,
                        trace_header_extensions=extension_count,
                        trace_edit=parsed["trace_edit"],
                        extended_channel_set=parsed["extended_channel_set"],
                        extended_file_number=parsed["extended_file_number"],
                        receiver_line=receiver_line,
                        receiver_point=receiver_point,
                        receiver_index=receiver_index,
                        sensor_type=sensor_type,
                        sample_count=sample_count,
                        sample_interval_ms=descriptor.sample_interval,
                        channel_type=descriptor.channel_type,
                    )
                )

                physical_index += 1
                offset = data_end
                if physical_index == expected_traces or physical_index % progress_step == 0:
                    percent = 12 + int(76 * physical_index / expected_traces)
                    self._report_progress(percent, f"Indexing traces: {physical_index:,}/{expected_traces:,}")

        return traces

    def _parse_trace_header(self, block: bytes) -> Dict[str, int]:
        if len(block) != self.TRACE_HEADER_SIZE:
            raise ValueError("A SEG-D trace header is incomplete.")

        file_number = self._decode_bcd(block[0:2], allow_f=True)
        scan_type = self._decode_bcd(block[2:3], allow_f=True)
        channel_set = self._decode_bcd(block[3:4], allow_f=True)
        trace_number = self._decode_bcd(block[4:6], allow_f=True)
        extended_channel_set = self._decode_uint(block[15:17])
        extended_file_number = self._decode_uint(block[17:20])

        if file_number < 0:
            file_number = extended_file_number
        if channel_set == 255 and extended_channel_set > 0:
            channel_set = extended_channel_set

        return {
            "file_number": file_number,
            "scan_type": scan_type,
            "channel_set": channel_set,
            "trace_number": trace_number,
            "trace_header_extensions": int(block[9]),
            "trace_edit": int(block[11]),
            "extended_channel_set": extended_channel_set,
            "extended_file_number": extended_file_number,
        }

    def _infer_sample_count_from_remaining(
        self,
        data_offset: int,
        descriptor: SegdChannelSetDescriptor,
        traces_remaining_in_set: int,
    ) -> int:
        if traces_remaining_in_set <= 0:
            return 0
        if descriptor.sample_count > 0:
            return descriptor.sample_count
        remaining_bytes = self.file_size - data_offset
        per_trace = remaining_bytes // traces_remaining_in_set
        extension_bytes = descriptor.trace_header_extensions * self.TRACE_EXTENSION_SIZE
        payload_bytes = per_trace - self.TRACE_HEADER_SIZE - extension_bytes
        if payload_bytes <= 0:
            return 0
        return payload_bytes // self.SAMPLE_SIZE

    def _calculate_descriptor_sample_count(
        self,
        start_time_ms: float,
        end_time_ms: float,
        sample_interval_ms: float,
    ) -> int:
        if sample_interval_ms <= 0 or end_time_ms < start_time_ms:
            return 0
        duration = end_time_ms - start_time_ms
        return int(round(duration / sample_interval_ms)) + 1

    def _resolve_primary_sample_interval(self) -> float:
        seismic_intervals = [
            item.sample_interval
            for item in self.channel_set_descriptors
            if item.channel_type == 1 and item.sample_interval > 0
        ]
        if seismic_intervals:
            return min(seismic_intervals)
        intervals = [item.sample_interval for item in self.channel_set_descriptors if item.sample_interval > 0]
        if intervals:
            return min(intervals)
        return self._base_scan_interval_ms

    def get_trace_count(self) -> int:
        return self._trace_count

    def get_sample_count(self) -> int:
        return self._sample_count

    def get_channel_count(self) -> int:
        return self._channel_count

    def get_sample_interval(self) -> float:
        return self._sample_interval

    def get_format_code(self) -> int:
        return self._gh1["format_code"]

    def get_revision(self) -> str:
        return f"{self._revision_major}.{self._revision_minor}"

    def get_aux_trace_count(self) -> int:
        return self._aux_trace_count

    def get_seismic_trace_count(self) -> int:
        return self._seismic_trace_count

    def get_trace_info(self, trace_index: int, decode_extensions: bool = True) -> SegdTraceInfo:
        if trace_index < 0 or trace_index >= self._trace_count:
            raise IndexError("Trace index out of range.")
        info = self._trace_index[trace_index]
        if decode_extensions and not info.extensions_decoded:
            self._decode_trace_extensions(info)
        return info

    def read_trace_window(
        self,
        trace_range: Tuple[int, int],
        sample_range: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        start_trace, end_trace = trace_range
        start_trace = max(0, min(int(start_trace), self._trace_count))
        end_trace = max(start_trace, min(int(end_trace), self._trace_count))

        if sample_range is None:
            start_sample = 0
            end_sample = self._sample_count
        else:
            start_sample, end_sample = sample_range
            start_sample = max(0, min(int(start_sample), self._sample_count))
            end_sample = max(start_sample, min(int(end_sample), self._sample_count))

        trace_count = end_trace - start_trace
        sample_count = end_sample - start_sample
        if trace_count <= 0 or sample_count <= 0:
            return np.empty((0, 1, 0), dtype=np.float32)

        output = np.zeros((trace_count, 1, sample_count), dtype=np.float32)

        for output_index, trace_index in enumerate(range(start_trace, end_trace)):
            trace = self._trace_index[trace_index]
            local_start = min(start_sample, trace.sample_count)
            local_end = min(end_sample, trace.sample_count)
            if local_end <= local_start:
                continue

            byte_start = trace.data_offset + local_start * self.SAMPLE_SIZE
            sample_total = local_end - local_start
            samples = self._read_float32_samples(byte_start, sample_total)
            if samples.size == 0:
                continue
            samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
            destination_start = local_start - start_sample
            destination_end = destination_start + len(samples)
            output[output_index, 0, destination_start:destination_end] = samples

        return output

    def read_channel_data(
        self,
        trace_range: Tuple[int, int],
        channel: int,
        sample_range: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        if channel != 0:
            raise IndexError("SEG-D demultiplexed physical traces expose one sample channel per trace.")
        data = self.read_trace_window(trace_range, sample_range)
        if data.size == 0:
            return np.empty((0, 0), dtype=np.float32)
        return data[:, 0, :]

    def read_trace_headers(self, trace_range: Tuple[int, int]) -> np.ndarray:
        start_trace, end_trace = trace_range
        start_trace = max(0, min(int(start_trace), self._trace_count))
        end_trace = max(start_trace, min(int(end_trace), self._trace_count))

        dtype = np.dtype(
            [
                ("physical_index", ">i4"),
                ("file_number", ">i4"),
                ("scan_type", ">i4"),
                ("channel_set", ">i4"),
                ("trace_number", ">i4"),
                ("trace_header_extensions", ">i4"),
                ("trace_edit", ">i4"),
                ("receiver_line", ">f8"),
                ("receiver_point", ">f8"),
                ("receiver_index", ">i4"),
                ("sensor_type", ">i4"),
                ("sample_count", ">i4"),
                ("sample_interval_ms", ">f8"),
                ("channel_type", ">i4"),
                ("header_offset", ">i8"),
                ("data_offset", ">i8"),
            ]
        )
        result = np.zeros(end_trace - start_trace, dtype=dtype)

        for output_index, trace_index in enumerate(range(start_trace, end_trace)):
            trace = self._trace_index[trace_index]
            result[output_index] = (
                trace.physical_index,
                trace.file_number,
                trace.scan_type,
                trace.channel_set,
                trace.trace_number,
                trace.trace_header_extensions,
                trace.trace_edit,
                trace.receiver_line,
                trace.receiver_point,
                trace.receiver_index,
                trace.sensor_type,
                trace.sample_count,
                trace.sample_interval_ms,
                trace.channel_type,
                trace.header_offset,
                trace.data_offset,
            )

        return result

    def _decode_trace_extensions(self, info: SegdTraceInfo) -> None:
        """Decode standard and Sercel trace-header extension blocks lazily.

        Blocks #2-#5 carry receiver coordinates and field-unit QC measurements
        in common Sercel 408/428 SEG-D records. Decoding is lazy so opening large
        files stays fast; only traces inspected by the user pay this cost.
        """
        try:
            count = max(0, min(15, int(info.trace_header_extensions)))
            base = info.header_offset + self.TRACE_HEADER_SIZE
            blocks = [
                self._read_bytes(base + index * self.TRACE_EXTENSION_SIZE, self.TRACE_EXTENSION_SIZE)
                for index in range(count)
            ]

            # Extension #1: SEG-D standard receiver identity. Use extended
            # line/point values when the compact 24-bit field is saturated.
            if len(blocks) >= 1 and len(blocks[0]) == 32:
                block = blocks[0]
                compact_line = self._decode_uint(block[0:3])
                compact_point = self._decode_uint(block[3:6])
                extended_line = self._decode_uint(block[10:13]) + self._decode_fraction(block[13:15])
                extended_point = self._decode_uint(block[15:18]) + self._decode_fraction(block[18:20])
                if compact_line == 0xFFFFFF or info.receiver_line in (0, -1):
                    info.receiver_line = extended_line
                if compact_point == 0xFFFFFF or info.receiver_point in (0, -1):
                    info.receiver_point = extended_point
                info.sensor_type = int(block[20]) or info.sensor_type

            # Extension #2: common Sercel receiver coordinates.
            if len(blocks) >= 2 and len(blocks[1]) == 32:
                block = blocks[1]
                info.receiver_x = self._finite_number(self._decode_float64(block[0:8]))
                info.receiver_y = self._finite_number(self._decode_float64(block[8:16]))
                info.receiver_elevation = self._finite_number(self._decode_float32(block[16:20]))
                info.sensor_type = int(block[20]) or info.sensor_type

            flags: list[str] = []

            # Extension #3: resistance and tilt QC.
            if len(blocks) >= 3 and len(blocks[2]) == 32:
                block = blocks[2]
                info.resistance_low_limit = self._finite_number(self._decode_float32(block[0:4]))
                info.resistance_high_limit = self._finite_number(self._decode_float32(block[4:8]))
                info.resistance = self._finite_number(self._decode_float32(block[8:12]))
                info.tilt_limit = self._finite_number(self._decode_float32(block[12:16]))
                info.tilt = self._finite_number(self._decode_float32(block[16:20]))
                if bool(block[20]):
                    flags.append("Resistance")
                if bool(block[21]):
                    flags.append("Tilt")

            # Extension #4: capacitance QC.
            if len(blocks) >= 4 and len(blocks[3]) == 32:
                block = blocks[3]
                info.capacitance_low_limit = self._finite_number(self._decode_float32(block[0:4]))
                info.capacitance_high_limit = self._finite_number(self._decode_float32(block[4:8]))
                info.capacitance = self._finite_number(self._decode_float32(block[8:12]))
                if bool(block[24]):
                    flags.append("Capacitance")

            # Extension #5: leakage QC and instrument position fallback.
            if len(blocks) >= 5 and len(blocks[4]) == 32:
                block = blocks[4]
                info.leakage_limit = self._finite_number(self._decode_float32(block[0:4]))
                info.leakage = self._finite_number(self._decode_float32(block[4:8]))
                info.instrument_longitude = self._finite_number(self._decode_float64(block[8:16]))
                info.instrument_latitude = self._finite_number(self._decode_float64(block[16:24]))
                elevation_mm = self._finite_number(self._decode_float32(block[28:32]))
                info.instrument_elevation = elevation_mm / 1000.0 if elevation_mm is not None else None
                if bool(block[24]):
                    flags.append("Leakage")

                # Some 428 exports populate instrument geographic position while
                # extension #2 receiver coordinates are zero/unset. Expose a useful
                # X/Y/Z fallback rather than blank values.
                if self._is_missing_coordinate(info.receiver_x):
                    info.receiver_x = info.instrument_longitude
                if self._is_missing_coordinate(info.receiver_y):
                    info.receiver_y = info.instrument_latitude
                if self._is_missing_coordinate(info.receiver_elevation):
                    info.receiver_elevation = info.instrument_elevation

            info.qc_flags = tuple(dict.fromkeys(flags))
        finally:
            info.extensions_decoded = True

    @staticmethod
    def _decode_float32(data: bytes) -> float:
        if len(data) != 4:
            return float("nan")
        return float(np.frombuffer(data, dtype=">f4", count=1)[0])

    @staticmethod
    def _decode_float64(data: bytes) -> float:
        if len(data) != 8:
            return float("nan")
        return float(np.frombuffer(data, dtype=">f8", count=1)[0])

    @staticmethod
    def _decode_fraction(data: bytes) -> float:
        if len(data) != 2:
            return 0.0
        raw = int.from_bytes(data, byteorder="big", signed=True)
        return raw / 65536.0

    @staticmethod
    def _finite_number(value: float) -> Optional[float]:
        return float(value) if np.isfinite(value) else None

    @staticmethod
    def _is_missing_coordinate(value: Optional[float]) -> bool:
        return value is None or not np.isfinite(value) or abs(float(value)) <= 1e-20

    def _read_float32_samples(self, byte_start: int, sample_count: int) -> np.ndarray:
        if sample_count <= 0 or byte_start < 0 or byte_start >= self.file_size:
            return np.empty(0, dtype=np.float32)
        available = max(0, (self.file_size - byte_start) // self.SAMPLE_SIZE)
        count = min(int(sample_count), int(available))
        if count <= 0:
            return np.empty(0, dtype=np.float32)
        # Read directly from the memory map instead of allocating an intermediate
        # bytes object for every trace. This substantially reduces large-file I/O
        # overhead and garbage collection pressure.
        endian = getattr(self, "_sample_endian", ">")
        view = np.frombuffer(self._memmap, dtype=f"{endian}f4", count=count, offset=int(byte_start))
        return view.astype(np.float32, copy=False)

    def _report_progress(self, value: int, message: str) -> None:
        callback = self._progress_callback
        if callback is None:
            return
        try:
            callback(max(0, min(100, int(value))), str(message))
        except Exception:
            pass

    def metadata_summary(self) -> Dict[str, Any]:
        return {
            "file": str(self.file_path),
            "file_size": self.file_size,
            "file_number": self.general_header_1.file_number,
            "format_code": self.get_format_code(),
            "revision": self.get_revision(),
            "manufacturer_code": self.general_header_1.manufacturer_code,
            "trace_count": self.get_trace_count(),
            "seismic_trace_count": self.get_seismic_trace_count(),
            "aux_trace_count": self.get_aux_trace_count(),
            "sample_count": self.get_sample_count(),
            "sample_interval_ms": self.get_sample_interval(),
            "channel_set_count": len(self.channel_set_descriptors),
            "data_start_offset": self._data_start_offset,
        }

    def close(self) -> None:
        memmap = getattr(self, "_memmap", None)
        if memmap is None:
            return
        mmap_object = getattr(memmap, "_mmap", None)
        if mmap_object is not None:
            try:
                mmap_object.close()
            except Exception:
                pass
        self._memmap = None

    def _read_bytes(self, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0 or offset >= self.file_size:
            return b""
        end = min(self.file_size, offset + length)
        return self._memmap[offset:end].tobytes()

    def _decode_bcd(self, data: bytes, allow_f: bool) -> int:
        digits: List[int] = []
        for value in data:
            high = (value >> 4) & 0x0F
            low = value & 0x0F
            for nibble in (high, low):
                if nibble <= 9:
                    digits.append(nibble)
                elif allow_f and nibble == 0x0F:
                    return -1 if all(((byte >> 4) & 0x0F) == 0x0F and (byte & 0x0F) == 0x0F for byte in data) else 255
                else:
                    raise ValueError(f"Invalid packed BCD value: {data.hex().upper()}")
        value = 0
        for digit in digits:
            value = value * 10 + digit
        return value

    def _decode_uint(self, data: bytes) -> int:
        return int.from_bytes(data, byteorder="big", signed=False)

    def _decode_int24(self, data: bytes) -> int:
        if len(data) != 3:
            return 0
        value = int.from_bytes(data, byteorder="big", signed=False)
        if value & 0x800000:
            value -= 1 << 24
        return value

    def _decode_int8(self, value: int) -> int:
        return value - 256 if value & 0x80 else value

    def _full_year(self, two_digit_year: int) -> int:
        if two_digit_year < 0:
            return 0
        return 2000 + two_digit_year if two_digit_year < 70 else 1900 + two_digit_year

    def _format_julian_date(self, year: int, julian_day: int) -> str:
        if year <= 0 or julian_day <= 0 or julian_day > 366:
            return f"Year {year}, Day {julian_day}"
        try:
            date_value = datetime(year, 1, 1) + timedelta(days=julian_day - 1)
            return date_value.strftime("%Y-%m-%d")
        except ValueError:
            return f"Year {year}, Day {julian_day}"
