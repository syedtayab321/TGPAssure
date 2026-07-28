from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class DisplayGrid:
    start_ms: float
    end_ms: float
    interval_ms: float
    sample_count: int


def choose_display_interval_ms(sample_intervals_us: Sequence[float]) -> float:
    """Return a stable positive display interval from trace header values.

    The modal interval is preferred because SEG-Y trace headers can legally
    override the binary header and a small number of anomalous traces should
    not redefine the whole display grid.
    """
    values = np.asarray(sample_intervals_us, dtype=np.float64)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        raise ValueError("No valid SEG-Y sample interval is available")
    # Quantize only at sub-nanosecond precision to make modal selection stable
    # without destroying Rev-1/2 IEEE-double microsecond sample intervals.
    quantized = np.round(values, decimals=6)
    uniq, counts = np.unique(quantized, return_counts=True)
    return float(uniq[int(np.argmax(counts))]) / 1000.0


def build_time_grid(
    sample_counts: Sequence[int],
    sample_intervals_us: Sequence[float],
    delay_times_ms: Sequence[int],
    *,
    interval_ms: float | None = None,
) -> DisplayGrid:
    counts = np.asarray(sample_counts, dtype=np.int64)
    intervals = np.asarray(sample_intervals_us, dtype=np.float64) / 1000.0
    delays = np.asarray(delay_times_ms, dtype=np.float64)
    if not (counts.size == intervals.size == delays.size) or counts.size == 0:
        raise ValueError("Trace timing arrays must be non-empty and have equal length")
    valid = (counts > 0) & (intervals > 0) & np.isfinite(intervals) & np.isfinite(delays)
    if not np.any(valid):
        raise ValueError("No valid trace timing information is available")
    counts = counts[valid]
    intervals = intervals[valid]
    delays = delays[valid]
    dt = float(interval_ms if interval_ms is not None else choose_display_interval_ms(intervals * 1000.0))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("Display sample interval must be positive")
    start = float(np.min(delays))
    ends = delays + np.maximum(counts - 1, 0) * intervals
    end = float(np.max(ends))
    samples = max(1, int(np.floor((end - start) / dt + 0.5)) + 1)
    return DisplayGrid(start_ms=start, end_ms=start + (samples - 1) * dt, interval_ms=dt, sample_count=samples)


def align_traces_to_time_grid(
    traces: Sequence[np.ndarray],
    sample_intervals_us: Sequence[float],
    delay_times_ms: Sequence[int],
    grid: DisplayGrid,
    start_sample: int = 0,
    end_sample: int | None = None,
) -> np.ndarray:
    """Align traces on true SEG-Y trace timing using linear interpolation.

    Missing samples are represented by NaN, never zero-filled, so variable
    length traces do not create false flat seismic events in the display.
    """
    intervals = np.asarray(sample_intervals_us, dtype=np.float64) / 1000.0
    delays = np.asarray(delay_times_ms, dtype=np.float64)
    if len(traces) != intervals.size or len(traces) != delays.size:
        raise ValueError("Trace data and timing arrays must have equal length")
    lo = max(0, int(start_sample))
    hi = grid.sample_count if end_sample is None else min(grid.sample_count, int(end_sample))
    if hi <= lo:
        return np.empty((len(traces), 0), dtype=np.float32)
    target_t = grid.start_ms + np.arange(lo, hi, dtype=np.float64) * grid.interval_ms
    out = np.full((len(traces), target_t.size), np.nan, dtype=np.float32)
    for i, trace in enumerate(traces):
        values = np.asarray(trace, dtype=np.float64)
        dt = float(intervals[i])
        delay = float(delays[i])
        if values.size == 0 or not np.isfinite(dt) or dt <= 0 or not np.isfinite(delay):
            continue
        source_t = delay + np.arange(values.size, dtype=np.float64) * dt
        finite = np.isfinite(values)
        if not np.any(finite):
            continue
        first = int(np.searchsorted(target_t, source_t[finite][0], side="left"))
        last = int(np.searchsorted(target_t, source_t[finite][-1], side="right"))
        if last <= first:
            continue
        if finite.all():
            out[i, first:last] = np.interp(target_t[first:last], source_t, values).astype(np.float32)
        else:
            out[i, first:last] = np.interp(target_t[first:last], source_t[finite], values[finite]).astype(np.float32)
    return out


def trace_rms(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    return float(np.sqrt(np.mean(finite * finite))) if finite.size else float("nan")


def apply_display_gain(data: np.ndarray, mode: str, interval_ms: float, agc_window_ms: float = 100.0) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32).copy()
    if arr.size == 0:
        return arr
    valid = np.isfinite(arr)
    if mode == "balance":
        for i in range(arr.shape[0]):
            rms = trace_rms(arr[i])
            if np.isfinite(rms) and rms > 1e-12:
                arr[i, valid[i]] /= rms
    elif mode == "agc":
        window = max(3, int(round(float(agc_window_ms) / max(float(interval_ms), 1e-9))))
        kernel = np.ones(window, dtype=np.float64) / window
        for i in range(arr.shape[0]):
            x = arr[i].astype(np.float64)
            mask = np.isfinite(x)
            if not np.any(mask):
                continue
            x0 = np.where(mask, x, 0.0)
            weight = np.convolve(mask.astype(np.float64), kernel, mode="same")
            power = np.convolve(x0 * x0, kernel, mode="same")
            rms = np.sqrt(np.divide(power, weight, out=np.zeros_like(power), where=weight > 1e-12))
            good = mask & (rms > 1e-12)
            arr[i, good] = (x[good] / rms[good]).astype(np.float32)
    return arr


def normalize_for_display(data: np.ndarray, percentile: float = 99.0) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32).copy()
    finite = np.abs(arr[np.isfinite(arr)])
    if finite.size == 0:
        return arr
    clip = float(np.percentile(finite, float(percentile)))
    if not np.isfinite(clip) or clip <= 1e-12:
        clip = 1.0
    arr[np.isfinite(arr)] = np.clip(arr[np.isfinite(arr)] / clip, -1.0, 1.0)
    return arr
