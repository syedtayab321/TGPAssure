from __future__ import annotations

import math
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np

from ..segy_reader import SegyReader, SegyTraceIndex

try:
    from scipy.signal import resample_poly
except Exception:  # pragma: no cover - SciPy is a normal TGPAssure dependency
    resample_poly = None


@dataclass(frozen=True)
class SegdConversionOptions:
    """Controls for standards-aware SEG-Y -> SEG-D conversion.

    TGPAssure writes a conservative SEG-D Rev 2.1 demultiplexed subset using
    format code 8058 (big-endian 32-bit IEEE float samples). Rev 2.1 is chosen
    because it is broadly interoperable and is fully supported by TGPAssure's
    SEG-D reader. Manufacturer-proprietary acquisition headers are never
    fabricated.
    """

    destination_sample_rate_hz: Optional[float] = None
    amplitude_scale: float = 1.0
    file_number: Optional[int] = None
    preserve_trace_timing: bool = True
    antialias: bool = True
    validate_output: bool = True


@dataclass
class SegdConversionReport:
    input_path: Path
    output_path: Path
    trace_count: int
    source_sample_intervals_us: tuple[int, ...]
    output_sample_interval_us: int
    resampled_trace_count: int
    minimum_samples: int
    maximum_samples: int
    nonfinite_samples_replaced: int
    file_number: int
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class SegdWriter:
    """Atomic SEG-D Rev 2.1 writer for demultiplexed IEEE float traces.

    The writer intentionally emits only fields that can be derived reliably
    from SEG-Y. Unknown manufacturer/acquisition metadata remains zero/unspecified
    rather than being invented. Each trace carries one 32-byte trace-header
    extension with receiver line/point and exact sample count.
    """

    GENERAL_HEADER_BYTES = 64  # GH1 + GH2 in Rev 2.1
    CHANNEL_DESCRIPTOR_BYTES = 32
    TRACE_HEADER_BYTES = 20
    TRACE_EXTENSION_BYTES = 32
    FORMAT_CODE = 8058
    MAX_TRACES_PER_SET = 9999
    MAX_CHANNEL_SETS = 99

    def __init__(self, out_path: Path) -> None:
        self.out_path = Path(out_path).expanduser().resolve()
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._part = self.out_path.with_name(self.out_path.name + ".part")
        self._closed = False
        self._finalized = False
        self.f = self._part.open("wb")
        self.actual_sample_interval_us: Optional[int] = None

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SEG-D writer is already closed")

    @staticmethod
    def _bcd(value: int, byte_count: int) -> bytes:
        value = int(value)
        max_value = (10 ** (byte_count * 2)) - 1
        if not 0 <= value <= max_value:
            raise ValueError(f"BCD value {value} does not fit in {byte_count} byte(s)")
        digits = f"{value:0{byte_count * 2}d}"
        return bytes((int(digits[i]) << 4) | int(digits[i + 1]) for i in range(0, len(digits), 2))

    @staticmethod
    def _encode_interval(sample_interval_us: int) -> tuple[int, int, int]:
        """Encode Rev 2.1 base scan interval and subscan exponent.

        Base scan interval is stored in 1/16 ms units. The channel-set subscan
        exponent divides that interval by 2**n. We search all legal exponents
        and reject an interval if metadata would differ materially from the
        requested timing.
        """
        target_ms = float(sample_interval_us) / 1000.0
        if target_ms <= 0:
            raise ValueError("Sample interval must be positive")
        best: tuple[float, int, int, float] | None = None
        for exponent in range(16):
            byte_value = int(round(target_ms * 16.0 * (2 ** exponent)))
            if not 1 <= byte_value <= 255:
                continue
            actual_ms = (byte_value / 16.0) / float(2 ** exponent)
            candidate = (abs(actual_ms - target_ms), byte_value, exponent, actual_ms)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            raise ValueError(
                f"Sample interval {sample_interval_us} us cannot be represented in SEG-D Rev 2.1 base/subscan fields"
            )
        error, base_byte, exponent, actual_ms = best
        tolerance_ms = max(0.0005, target_ms * 0.001)  # 0.5 us or 0.1%
        if error > tolerance_ms:
            raise ValueError(
                f"Sample interval {sample_interval_us} us is not accurately representable in SEG-D Rev 2.1 "
                f"(nearest {actual_ms * 1000.0:.3f} us)"
            )
        return base_byte, exponent, int(round(actual_ms * 1000.0))

    def write_headers(
        self,
        *,
        file_number: int,
        channel_set_counts: list[int],
        sample_interval_us: int,
        nominal_sample_count: int,
        record_datetime: Optional[datetime] = None,
    ) -> None:
        self._ensure_open()
        if not channel_set_counts or any(count <= 0 or count > self.MAX_TRACES_PER_SET for count in channel_set_counts):
            raise ValueError("Each SEG-D channel set must contain between 1 and 9,999 traces")
        if len(channel_set_counts) > self.MAX_CHANNEL_SETS:
            raise ValueError("SEG-D Rev 2.1 conversion supports at most 99 channel sets in one record")

        base_byte, exponent, actual_interval_us = self._encode_interval(sample_interval_us)
        self.actual_sample_interval_us = actual_interval_us
        now = record_datetime or datetime.now()
        julian = int(now.strftime("%j"))

        gh1 = bytearray(32)
        gh1[0:2] = self._bcd(int(file_number), 2) if int(file_number) <= 9999 else b"\xFF\xFF"
        gh1[2:4] = self._bcd(self.FORMAT_CODE, 2)
        gh1[10:11] = self._bcd(now.year % 100, 1)
        # high nibble = number of additional general-header blocks (GH2 only)
        # low nibble = hundreds digit of Julian day.
        gh1[11] = (1 << 4) | (julian // 100)
        gh1[12:13] = self._bcd(julian % 100, 1)
        gh1[13:14] = self._bcd(now.hour, 1)
        gh1[14:15] = self._bcd(now.minute, 1)
        gh1[15:16] = self._bcd(now.second, 1)
        gh1[16:17] = self._bcd(0, 1)       # manufacturer: unspecified
        gh1[17:19] = self._bcd(0, 2)       # manufacturer serial: unspecified
        gh1[22] = base_byte
        gh1[25] = 0x80                     # normal seismic record
        gh1[27:28] = self._bcd(1, 1)       # one scan type
        gh1[28:29] = self._bcd(len(channel_set_counts), 1)
        gh1[29:30] = self._bcd(0, 1)       # skew blocks
        gh1[30:31] = self._bcd(0, 1)       # extended headers
        gh1[31:32] = self._bcd(0, 1)       # external headers

        gh2 = bytearray(32)
        gh2[0:3] = int(file_number).to_bytes(3, "big", signed=False)
        gh2[3:5] = len(channel_set_counts).to_bytes(2, "big", signed=False)
        gh2[10] = 2
        gh2[11] = 1
        gh2[18] = 2                        # block number
        gh2[20:22] = (1).to_bytes(2, "big")

        self.f.write(gh1)
        self.f.write(gh2)

        duration_ms = max(0.0, (max(1, int(nominal_sample_count)) - 1) * actual_interval_us / 1000.0)
        end_time_units = min(0xFFFF, int(round(duration_ms / 2.0)))
        for set_index, channel_count in enumerate(channel_set_counts, start=1):
            descriptor = bytearray(self.CHANNEL_DESCRIPTOR_BYTES)
            descriptor[0:1] = self._bcd(1, 1)
            descriptor[1:2] = self._bcd(set_index, 1)
            descriptor[2:4] = (0).to_bytes(2, "big")
            descriptor[4:6] = end_time_units.to_bytes(2, "big")
            descriptor[8:10] = self._bcd(channel_count, 2)
            descriptor[10] = 0x10          # seismic channel type
            descriptor[11] = (exponent & 0x0F) << 4
            descriptor[12:14] = self._bcd(0, 2)
            descriptor[26:28] = set_index.to_bytes(2, "big")
            descriptor[28] = 0x01          # one trace-header extension
            self.f.write(descriptor)

    def write_trace(
        self,
        *,
        original_trace_index: int,
        channel_set: int,
        trace_number: int,
        samples: np.ndarray,
        receiver_line: int = 0,
        receiver_point: int = 0,
        file_number: int = 1,
    ) -> None:
        self._ensure_open()
        values = np.asarray(samples, dtype=np.float32).reshape(-1)
        if values.size > 0xFFFFFF:
            raise ValueError("A SEG-D trace cannot store more than 16,777,215 samples in this trace extension")

        header = bytearray(self.TRACE_HEADER_BYTES)
        header[0:2] = self._bcd(int(file_number), 2) if int(file_number) <= 9999 else b"\xFF\xFF"
        header[2:3] = self._bcd(1, 1)
        header[3:4] = self._bcd(channel_set, 1)
        header[4:6] = self._bcd(trace_number, 2)
        header[9] = 1
        header[15:17] = int(channel_set).to_bytes(2, "big", signed=False)
        header[17:20] = int(file_number).to_bytes(3, "big", signed=False)

        extension = bytearray(self.TRACE_EXTENSION_BYTES)
        extension[0:3] = max(0, min(0xFFFFFE, int(receiver_line))).to_bytes(3, "big")
        extension[3:6] = max(0, min(0xFFFFFE, int(receiver_point))).to_bytes(3, "big")
        extension[6] = int(original_trace_index) & 0xFF
        extension[7:10] = int(values.size).to_bytes(3, "big", signed=False)
        extension[20] = 1                  # generic seismic sensor type

        self.f.write(header)
        self.f.write(extension)
        self.f.write(values.astype(">f4", copy=False).tobytes())

    def finalize(self) -> None:
        if self._finalized:
            return
        self._ensure_open()
        self.f.flush()
        try:
            os.fsync(self.f.fileno())
        except OSError:
            pass
        self.f.close()
        self._closed = True
        self._part.replace(self.out_path)
        self._finalized = True

    def abort_and_cleanup(self) -> None:
        if not self._closed:
            try:
                self.f.close()
            finally:
                self._closed = True
        try:
            self._part.unlink(missing_ok=True)
        except OSError:
            pass


class SegyToSegdConverter:
    """Standards-aware SEG-Y -> SEG-D Rev 2.1 / 8058 converter."""

    def inspect_source(self, segy_path: Path) -> dict:
        reader = SegyReader(Path(segy_path))
        index = reader.scan_trace_headers()
        intervals = sorted({int(v) for v in index.sample_intervals_us if int(v) > 0})
        if not intervals and int(reader.binary_header.sample_interval_us) > 0:
            intervals = [int(reader.binary_header.sample_interval_us)]
        counts = np.asarray(index.sample_counts, dtype=np.int64)
        return {
            "path": str(Path(segy_path).resolve()),
            "trace_count": index.trace_count,
            "sample_format": reader.binary_header.sample_format_code,
            "sample_intervals_us": intervals,
            "minimum_samples": int(counts.min()) if counts.size else 0,
            "maximum_samples": int(counts.max()) if counts.size else 0,
            "segy_revision": reader.binary_header.revision,
            "job_id": int(reader.binary_header.job_id),
            "line_number": int(reader.binary_header.line_number),
            "reel_number": int(reader.binary_header.reel_number),
            "byte_order": "big-endian" if reader.binary_header.endian == ">" else "little-endian",
        }

    def preview_first_trace(self, segy_path: Path) -> Optional[np.ndarray]:
        reader = SegyReader(Path(segy_path))
        index = reader.scan_trace_headers()
        if index.trace_count == 0:
            return None
        data = reader.read_trace(0, index)
        return np.asarray(data[: min(256, data.size)], dtype=np.float32)

    @staticmethod
    def _resample(samples: np.ndarray, src_rate_hz: float, dst_rate_hz: float, *, antialias: bool = True) -> np.ndarray:
        values = np.asarray(samples, dtype=np.float32).reshape(-1)
        if values.size <= 1:
            return values.copy()
        if src_rate_hz <= 0 or dst_rate_hz <= 0:
            raise ValueError("Source and destination sample rates must be positive")
        if np.isclose(src_rate_hz, dst_rate_hz, rtol=0.0, atol=1e-9):
            return values.copy()

        duration_s = (values.size - 1) / float(src_rate_hz)
        expected_count = max(1, int(round(duration_s * float(dst_rate_hz))) + 1)

        if antialias and resample_poly is not None:
            ratio = Fraction(dst_rate_hz / src_rate_hz).limit_denominator(100_000)
            result = resample_poly(values.astype(np.float64), ratio.numerator, ratio.denominator, padtype="line")
            result = np.asarray(result, dtype=np.float32)
            if result.size > expected_count:
                result = result[:expected_count]
            elif result.size < expected_count:
                pad_value = result[-1] if result.size else 0.0
                result = np.pad(result, (0, expected_count - result.size), constant_values=float(pad_value))
            return result

        src_times = np.arange(values.size, dtype=np.float64) / float(src_rate_hz)
        dst_times = np.arange(expected_count, dtype=np.float64) / float(dst_rate_hz)
        dst_times = np.minimum(dst_times, src_times[-1])
        return np.interp(dst_times, src_times, values).astype(np.float32)

    @staticmethod
    def _normalise_indices(trace_indices: Optional[Iterable[int]], index: SegyTraceIndex) -> list[int]:
        if trace_indices is None:
            return list(range(index.trace_count))
        result: list[int] = []
        seen: set[int] = set()
        for raw in trace_indices:
            value = int(raw)
            if value < 0 or value >= index.trace_count:
                raise IndexError(f"Trace index out of range: {value} (trace count {index.trace_count})")
            if value not in seen:
                result.append(value)
                seen.add(value)
        if not result:
            raise ValueError("At least one trace must be selected for conversion")
        return result

    @staticmethod
    def _source_interval_us(reader: SegyReader, index: SegyTraceIndex, trace_idx: int) -> int:
        trace_interval = int(index.sample_intervals_us[trace_idx])
        if trace_interval > 0:
            return trace_interval
        binary_interval = int(reader.binary_header.sample_interval_us)
        if binary_interval <= 0:
            raise ValueError(f"SEG-Y sample interval is missing or invalid for trace {trace_idx + 1}")
        return binary_interval

    @staticmethod
    def _channel_set_counts(total: int) -> list[int]:
        counts: list[int] = []
        remaining = int(total)
        while remaining > 0:
            count = min(SegdWriter.MAX_TRACES_PER_SET, remaining)
            counts.append(count)
            remaining -= count
        if len(counts) > SegdWriter.MAX_CHANNEL_SETS:
            raise ValueError(
                f"Selected trace count requires {len(counts)} channel sets; maximum supported is {SegdWriter.MAX_CHANNEL_SETS}"
            )
        return counts

    @staticmethod
    def _derive_file_number(reader: SegyReader, options: SegdConversionOptions) -> int:
        if options.file_number is not None:
            value = int(options.file_number)
        else:
            value = int(reader.binary_header.reel_number or reader.binary_header.line_number or reader.binary_header.job_id or 1)
        return max(1, min(value, 0xFFFFFF))

    @staticmethod
    def _derive_record_datetime(reader: SegyReader, index: SegyTraceIndex, first_idx: int) -> Optional[datetime]:
        try:
            year = int(index.year[first_idx])
            day = int(index.day_of_year[first_idx])
            hour = int(index.hour[first_idx])
            minute = int(index.minute[first_idx])
            second = int(index.second[first_idx])
            if year > 0 and 1 <= day <= 366:
                return datetime.strptime(f"{year:04d}-{day:03d} {hour:02d}:{minute:02d}:{second:02d}", "%Y-%j %H:%M:%S")
        except Exception:
            return None
        return None

    def convert(
        self,
        segy_path: Path,
        out_path: Path,
        trace_indices: Optional[Iterable[int]] = None,
        sample_rate: Optional[float] = None,
        scale: float = 1.0,
        gain: Optional[Callable[[np.ndarray], np.ndarray]] = None,
        progress_callback: Optional[Callable[[float, float], None]] = None,
        stop_event: Optional[threading.Event] = None,
        options: Optional[SegdConversionOptions] = None,
    ) -> SegdConversionReport:
        segy_path = Path(segy_path).expanduser().resolve()
        out_path = Path(out_path).expanduser().resolve()
        if segy_path == out_path:
            raise ValueError("Output path must be different from the input SEG-Y file")

        opts = options or SegdConversionOptions(
            destination_sample_rate_hz=sample_rate,
            amplitude_scale=scale,
        )
        if sample_rate is not None and options is not None:
            opts = SegdConversionOptions(**{**opts.__dict__, "destination_sample_rate_hz": float(sample_rate)})
        if scale != 1.0 and options is not None:
            opts = SegdConversionOptions(**{**opts.__dict__, "amplitude_scale": float(scale)})

        if opts.destination_sample_rate_hz is not None and float(opts.destination_sample_rate_hz) <= 0:
            raise ValueError("Destination sample rate must be positive")
        if not np.isfinite(float(opts.amplitude_scale)):
            raise ValueError("Amplitude scale must be finite")

        reader = SegyReader(segy_path)
        index = reader.scan_trace_headers()
        indices = self._normalise_indices(trace_indices, index)
        if index.truncated:
            raise ValueError("SEG-Y appears truncated; conversion is blocked to avoid producing an incomplete SEG-D file")

        first_index = indices[0]
        source_intervals = tuple(sorted({self._source_interval_us(reader, index, i) for i in indices}))
        first_interval_us = self._source_interval_us(reader, index, first_index)
        destination_rate_hz = (
            float(opts.destination_sample_rate_hz)
            if opts.destination_sample_rate_hz is not None
            else 1_000_000.0 / float(first_interval_us)
        )
        requested_interval_us = max(1, int(round(1_000_000.0 / destination_rate_hz)))

        # Nominal count is used only by the channel-set descriptor. Exact counts
        # are also stored per trace in Trace Header Extension #1.
        nominal_source_count = int(index.sample_counts[first_index])
        nominal_source_rate = 1_000_000.0 / float(first_interval_us)
        nominal_duration_s = max(0.0, (nominal_source_count - 1) / nominal_source_rate)
        nominal_output_count = max(1, int(round(nominal_duration_s * destination_rate_hz)) + 1)

        channel_counts = self._channel_set_counts(len(indices))
        file_number = self._derive_file_number(reader, opts)
        record_datetime = self._derive_record_datetime(reader, index, first_index)
        started = time.perf_counter()
        processed = 0
        resampled_count = 0
        nonfinite_replaced = 0
        sample_counts_out: list[int] = []
        warnings: list[str] = []
        if len(source_intervals) > 1:
            warnings.append(
                "Input SEG-Y contains multiple trace sample intervals; each trace was individually resampled to the selected SEG-D interval."
            )
        if opts.antialias and resample_poly is None:
            warnings.append("SciPy resample_poly is unavailable; linear interpolation fallback was used for resampling.")

        writer = SegdWriter(out_path)
        try:
            writer.write_headers(
                file_number=file_number,
                channel_set_counts=channel_counts,
                sample_interval_us=requested_interval_us,
                nominal_sample_count=nominal_output_count,
                record_datetime=record_datetime,
            )
            actual_interval_us = int(writer.actual_sample_interval_us or requested_interval_us)
            destination_rate_hz = 1_000_000.0 / float(actual_interval_us)

            for ordinal, trace_idx in enumerate(indices):
                if stop_event is not None and stop_event.is_set():
                    raise InterruptedError("SEG-Y to SEG-D conversion cancelled")

                samples = np.asarray(reader.read_trace(trace_idx, index), dtype=np.float32)
                trace_interval_us = self._source_interval_us(reader, index, trace_idx)
                trace_rate_hz = 1_000_000.0 / float(trace_interval_us)

                if gain is not None:
                    samples = np.asarray(gain(samples), dtype=np.float32).reshape(-1)
                if float(opts.amplitude_scale) != 1.0:
                    samples = samples * np.float32(opts.amplitude_scale)

                if not np.isclose(trace_rate_hz, destination_rate_hz, rtol=0.0, atol=1e-9):
                    samples = self._resample(samples, trace_rate_hz, destination_rate_hz, antialias=opts.antialias)
                    resampled_count += 1

                bad = int(samples.size - np.count_nonzero(np.isfinite(samples)))
                if bad:
                    nonfinite_replaced += bad
                    samples = np.nan_to_num(samples, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

                channel_set = ordinal // SegdWriter.MAX_TRACES_PER_SET + 1
                trace_number = ordinal % SegdWriter.MAX_TRACES_PER_SET + 1
                header = reader.read_trace_header(trace_idx, index)
                receiver_line = int(header.inline_3d or header.field_record or header.cdp or 0)
                receiver_point = int(header.crossline_3d or header.trace_number or header.cdp_trace or (trace_idx + 1))
                writer.write_trace(
                    original_trace_index=trace_idx,
                    channel_set=channel_set,
                    trace_number=trace_number,
                    samples=samples,
                    receiver_line=receiver_line,
                    receiver_point=receiver_point,
                    file_number=file_number,
                )
                sample_counts_out.append(int(samples.size))
                processed += 1

                elapsed = time.perf_counter() - started
                remaining = (elapsed / processed) * (len(indices) - processed) if processed else 0.0
                if progress_callback is not None:
                    progress_callback(processed / len(indices), max(0.0, remaining))

            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("SEG-Y to SEG-D conversion cancelled")
            writer.finalize()

            if opts.validate_output:
                self.validate_output(out_path, expected_trace_count=len(indices), expected_interval_us=actual_interval_us)

            return SegdConversionReport(
                input_path=segy_path,
                output_path=out_path,
                trace_count=len(indices),
                source_sample_intervals_us=source_intervals,
                output_sample_interval_us=actual_interval_us,
                resampled_trace_count=resampled_count,
                minimum_samples=min(sample_counts_out) if sample_counts_out else 0,
                maximum_samples=max(sample_counts_out) if sample_counts_out else 0,
                nonfinite_samples_replaced=nonfinite_replaced,
                file_number=file_number,
                warnings=warnings,
                elapsed_seconds=time.perf_counter() - started,
            )
        except BaseException:
            writer.abort_and_cleanup()
            try:
                if writer._finalized:
                    out_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def validate_output(out_path: Path, *, expected_trace_count: Optional[int] = None, expected_interval_us: Optional[int] = None) -> dict:
        from ..segd_viewer.segd_reader import SegdReader

        verifier = SegdReader(out_path)
        try:
            trace_count = verifier.get_trace_count()
            interval_us = int(round(verifier.get_sample_interval() * 1000.0))
            if expected_trace_count is not None and trace_count != int(expected_trace_count):
                raise ValueError(
                    f"Converted SEG-D validation indexed {trace_count} of {expected_trace_count} expected traces"
                )
            if expected_interval_us is not None and abs(interval_us - int(expected_interval_us)) > 1:
                raise ValueError(
                    f"Converted SEG-D validation found {interval_us} us sample interval; expected {expected_interval_us} us"
                )
            # Read first and last traces to verify payload offsets/sample decoding.
            if trace_count:
                verifier.read_channel_data((0, 1), 0)
                if trace_count > 1:
                    verifier.read_channel_data((trace_count - 1, trace_count), 0)
            return {
                "trace_count": trace_count,
                "sample_count": verifier.get_sample_count(),
                "sample_interval_us": interval_us,
                "format_code": verifier.get_format_code(),
                "revision": verifier.get_revision(),
            }
        finally:
            verifier.close()

    def batch_convert(self, inputs: Iterable[Path], out_dir: Path, **kwargs) -> list[SegdConversionReport]:
        destination = Path(out_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        stop_event = kwargs.get("stop_event")
        forwarded = {key: value for key, value in kwargs.items() if key != "stop_event"}
        reports: list[SegdConversionReport] = []
        for path in inputs:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("SEG-Y to SEG-D batch conversion cancelled")
            out_file = destination / f"{Path(path).stem}.segd"
            reports.append(self.convert(path, out_file, stop_event=stop_event, **forwarded))
        return reports
