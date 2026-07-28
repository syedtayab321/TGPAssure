from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.signal import hilbert

from core.domain.qc_engine import QCFinding, QCSeverity, QCStageResult, QCStatus


_EPS = np.finfo(np.float64).eps


@dataclass
class GatherData:
    key: str
    trace_indices: np.ndarray
    offsets_m: np.ndarray
    raw: np.ndarray
    normalized: np.ndarray
    dt_ms: float
    sample_step: int

    @property
    def sample_count(self) -> int:
        return int(self.raw.shape[1]) if self.raw.ndim == 2 else 0

    @property
    def times_ms(self) -> np.ndarray:
        return np.arange(self.sample_count, dtype=np.float64) * self.dt_ms


def threshold(context: Mapping[str, Any], key: str, default: float) -> float:
    values = context.get("thresholds") or {}
    try:
        return float(values.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def result_status(findings: Sequence[QCFinding]) -> QCStatus:
    severities = {finding.severity for finding in findings}
    if QCSeverity.CRITICAL in severities or QCSeverity.ERROR in severities:
        return QCStatus.FAIL
    if QCSeverity.WARNING in severities:
        return QCStatus.WARN
    return QCStatus.PASS


def stage_result(
    stage_name: str,
    metrics: Mapping[str, Any],
    findings: Optional[List[QCFinding]] = None,
) -> QCStageResult:
    items = findings or []
    return QCStageResult(
        stage_name=stage_name,
        status=result_status(items),
        summary_json=json.dumps(jsonable(dict(metrics)), sort_keys=True),
        findings=items,
    )


def error_result(stage_name: str, rule_id: str, error: Exception) -> QCStageResult:
    return QCStageResult(
        stage_name=stage_name,
        status=QCStatus.FAIL,
        summary_json=json.dumps({"error": str(error)}),
        findings=[
            make_finding(
                rule_id=rule_id,
                severity=QCSeverity.ERROR,
                message=f"{stage_name} failed: {error}",
                category="processing",
                title=f"{stage_name} execution failure",
                suggested_action="Verify the SEG-Y sorting, trace headers, sample interval, and available memory, then rerun the stage.",
                context={"exception_type": type(error).__name__},
            )
        ],
    )


def make_finding(
    rule_id: str,
    severity: QCSeverity,
    message: str,
    *,
    category: str,
    title: str,
    suggested_action: str,
    metric_name: Optional[str] = None,
    observed_value: Optional[float] = None,
    expected_min: Optional[float] = None,
    expected_max: Optional[float] = None,
    unit: Optional[str] = None,
    location_ref: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> QCFinding:
    metadata = {
        "category": category,
        "title": title,
        "metric_name": metric_name,
        "observed_value": observed_value,
        "expected_min": expected_min,
        "expected_max": expected_max,
        "unit": unit,
        "context": jsonable(dict(context or {})),
    }
    return QCFinding(
        rule_id=rule_id,
        severity=severity,
        message=message,
        location_ref=location_ref,
        suggested_action=suggested_action,
        metadata_json=json.dumps(metadata, sort_keys=True),
    )


def get_reader_and_index(context: Dict[str, Any]) -> Tuple[Any, Any]:
    reader = context.get("reader")
    if reader is None:
        raise ValueError("No SEG-Y reader is available in the QC context")
    index = context.get("index")
    if index is None:
        index = reader.scan_trace_headers()
        context["index"] = index
    if int(getattr(index, "trace_count", 0)) <= 0:
        raise ValueError("The SEG-Y file contains no readable traces")
    return reader, index


def robust_center_sigma(values: np.ndarray) -> Tuple[float, float]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 0.0, 0.0
    center = float(np.median(finite))
    mad = float(np.median(np.abs(finite - center)))
    return center, 1.4826 * mad


def robust_outlier_mask(values: np.ndarray, factor: float) -> np.ndarray:
    data = np.asarray(values, dtype=np.float64)
    center, sigma = robust_center_sigma(data)
    if sigma <= _EPS:
        return np.zeros(data.shape, dtype=bool)
    return np.isfinite(data) & (np.abs(data - center) > float(factor) * sigma)


def _group_values(index: Any) -> Tuple[np.ndarray, str]:
    trace_count = int(index.trace_count)
    cdp = np.asarray(index.cdp, dtype=np.int64)
    if np.count_nonzero(cdp) >= max(3, trace_count // 4):
        return cdp, "CDP"

    inline = np.asarray(index.inline_3d, dtype=np.int64)
    crossline = np.asarray(index.crossline_3d, dtype=np.int64)
    valid_3d = (inline != 0) | (crossline != 0)
    if np.count_nonzero(valid_3d) >= max(3, trace_count // 4):
        pairs = np.column_stack((inline, crossline))
        _, inverse = np.unique(pairs, axis=0, return_inverse=True)
        return inverse.astype(np.int64) + 1, "BIN"

    field_record = np.asarray(index.field_record, dtype=np.int64)
    if np.count_nonzero(field_record) >= max(3, trace_count // 4):
        return field_record, "FIELD_RECORD"

    return np.arange(trace_count, dtype=np.int64) + 1, "TRACE"


def select_gather_groups(
    index: Any,
    *,
    min_fold: int = 3,
    max_gathers: int = 12,
    max_traces_per_gather: int = 48,
) -> Tuple[List[Tuple[str, np.ndarray]], str]:
    group_values, group_type = _group_values(index)
    candidates: List[Tuple[str, np.ndarray]] = []
    for value in np.unique(group_values):
        if int(value) == 0:
            continue
        indices = np.flatnonzero(group_values == value)
        if indices.size < min_fold:
            continue
        if indices.size > max_traces_per_gather:
            order = np.argsort(np.abs(np.asarray(index.offsets)[indices]))
            ordered = indices[order]
            sample_positions = np.linspace(0, ordered.size - 1, max_traces_per_gather, dtype=int)
            indices = ordered[sample_positions]
        candidates.append((f"{group_type}:{int(value)}", indices.astype(np.int64)))

    if not candidates:
        return [], group_type

    candidates.sort(key=lambda item: int(item[1].size), reverse=True)
    if len(candidates) > max_gathers:
        positions = np.linspace(0, len(candidates) - 1, max_gathers, dtype=int)
        candidates = [candidates[int(pos)] for pos in positions]
    return candidates, group_type


def _measurement_scale_to_metres(reader: Any) -> float:
    system = int(getattr(getattr(reader, "binary_header", None), "measurement_system", 1) or 1)
    return 0.3048 if system == 2 else 1.0


def read_gather(
    reader: Any,
    index: Any,
    key: str,
    trace_indices: Sequence[int],
    *,
    max_samples: int = 1600,
) -> GatherData:
    indices = np.asarray(trace_indices, dtype=np.int64)
    if indices.size == 0:
        raise ValueError(f"Gather {key} has no traces")
    sample_counts = np.asarray(index.sample_counts, dtype=np.int64)[indices]
    common_samples = int(np.min(sample_counts))
    if common_samples < 8:
        raise ValueError(f"Gather {key} has fewer than 8 common samples")
    sample_step = max(1, int(math.ceil(common_samples / max_samples)))
    output_samples = int(math.ceil(common_samples / sample_step))
    raw = np.zeros((indices.size, output_samples), dtype=np.float64)

    for row, trace_index in enumerate(indices):
        trace = np.asarray(reader.read_trace(int(trace_index), index=index), dtype=np.float64)
        trace = trace[:common_samples:sample_step]
        finite = np.isfinite(trace)
        if not np.any(finite):
            continue
        replacement = float(np.median(trace[finite]))
        trace = np.where(finite, trace, replacement)
        raw[row, : trace.size] = trace

    demeaned = raw - np.mean(raw, axis=1, keepdims=True)
    rms = np.sqrt(np.mean(np.square(demeaned), axis=1, keepdims=True))
    normalized = np.divide(demeaned, np.maximum(rms, _EPS), out=np.zeros_like(demeaned), where=rms > _EPS)
    dt_values = np.asarray(index.sample_intervals_us, dtype=np.float64)[indices]
    positive_dt = dt_values[dt_values > 0]
    if positive_dt.size:
        dt_ms = float(np.median(positive_dt) / 1000.0) * sample_step
    else:
        dt_ms = float(getattr(reader.binary_header, "sample_interval_us", 1000) / 1000.0) * sample_step
    offsets_m = np.asarray(index.offsets, dtype=np.float64)[indices] * _measurement_scale_to_metres(reader)
    return GatherData(key, indices, offsets_m, demeaned, normalized, dt_ms, sample_step)


def fft_lag_samples(trace: np.ndarray, reference: np.ndarray, max_lag_samples: int) -> Tuple[int, float]:
    a = np.asarray(trace, dtype=np.float64)
    b = np.asarray(reference, dtype=np.float64)
    length = min(a.size, b.size)
    if length < 8:
        return 0, 0.0
    a = a[:length] - np.mean(a[:length])
    b = b[:length] - np.mean(b[:length])
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm <= _EPS:
        return 0, 0.0
    fft_size = 1 << int(math.ceil(math.log2(max(2, 2 * length - 1))))
    cross = np.fft.irfft(np.fft.rfft(a, fft_size) * np.conj(np.fft.rfft(b, fft_size)), fft_size)
    cross = np.concatenate((cross[-(length - 1):], cross[:length]))
    lags = np.arange(-(length - 1), length, dtype=np.int64)
    maximum = max(1, min(int(max_lag_samples), length - 1))
    valid = np.abs(lags) <= maximum
    selected = cross[valid]
    selected_lags = lags[valid]
    best = int(np.argmax(selected))
    return int(selected_lags[best]), float(selected[best] / norm)


def sample_semblance(gather: np.ndarray, smoothing_samples: int = 9) -> np.ndarray:
    data = np.asarray(gather, dtype=np.float64)
    if data.ndim != 2 or data.shape[0] == 0:
        return np.array([], dtype=np.float64)
    numerator = np.square(np.sum(data, axis=0))
    denominator = data.shape[0] * np.sum(np.square(data), axis=0) + _EPS
    values = np.clip(numerator / denominator, 0.0, 1.0)
    if smoothing_samples > 1 and values.size >= smoothing_samples:
        values = uniform_filter1d(values, size=smoothing_samples, mode="nearest")
    return values


def velocity_at_times(function: Mapping[str, Any], target_times_ms: np.ndarray) -> np.ndarray:
    times = np.asarray(function.get("times_ms", []), dtype=np.float64)
    velocities = np.asarray(function.get("velocities_m_s", []), dtype=np.float64)
    if times.size == 0 or velocities.size == 0:
        raise ValueError("Velocity function is empty")
    count = min(times.size, velocities.size)
    times = times[:count]
    velocities = velocities[:count]
    order = np.argsort(times)
    return np.interp(
        np.asarray(target_times_ms, dtype=np.float64),
        times[order],
        velocities[order],
        left=float(velocities[order][0]),
        right=float(velocities[order][-1]),
    )


def nmo_correct(
    gather: np.ndarray,
    offsets_m: np.ndarray,
    dt_ms: float,
    velocity_function: Mapping[str, Any],
) -> Tuple[np.ndarray, np.ndarray]:
    data = np.asarray(gather, dtype=np.float64)
    offsets = np.asarray(offsets_m, dtype=np.float64)
    if data.ndim != 2 or data.shape[0] != offsets.size:
        raise ValueError("Gather and offset dimensions do not match")
    samples = data.shape[1]
    output_times_ms = np.arange(samples, dtype=np.float64) * float(dt_ms)
    velocities = np.maximum(velocity_at_times(velocity_function, output_times_ms), 1.0)
    t0_s = output_times_ms / 1000.0
    corrected = np.zeros_like(data)
    stretches = np.zeros_like(data)
    sample_axis = np.arange(samples, dtype=np.float64)

    for row, offset in enumerate(offsets):
        input_time_s = np.sqrt(np.square(t0_s) + np.square(float(offset) / velocities))
        input_samples = input_time_s * 1000.0 / float(dt_ms)
        corrected[row] = np.interp(input_samples, sample_axis, data[row], left=0.0, right=0.0)
        denominator = np.maximum(t0_s, float(dt_ms) / 1000.0)
        stretches[row] = 100.0 * np.maximum(0.0, input_time_s - t0_s) / denominator
    return corrected, stretches


def section_from_context(
    context: Dict[str, Any],
    *,
    max_traces: int = 160,
    max_samples: int = 1800,
) -> Tuple[np.ndarray, float, List[str]]:
    stacks = context.get("brute_stacks") or []
    if stacks:
        ordered = sorted(stacks, key=lambda item: str(item.get("gather_key", "")))
        arrays = [np.asarray(item.get("stack"), dtype=np.float64) for item in ordered]
        arrays = [array for array in arrays if array.ndim == 1 and array.size >= 8]
        if arrays:
            common = min(array.size for array in arrays)
            sample_step = max(1, int(math.ceil(common / max_samples)))
            section = np.vstack([array[:common:sample_step] for array in arrays])
            dt_ms = float(ordered[0].get("dt_ms", 1.0)) * sample_step
            keys = [str(item.get("gather_key", idx)) for idx, item in enumerate(ordered[: len(arrays)])]
            return section, dt_ms, keys

    reader, index = get_reader_and_index(context)
    trace_count = int(index.trace_count)
    selected = np.linspace(0, trace_count - 1, min(max_traces, trace_count), dtype=int)
    common = int(np.min(np.asarray(index.sample_counts)[selected]))
    sample_step = max(1, int(math.ceil(common / max_samples)))
    traces = []
    for trace_index in selected:
        trace = np.asarray(reader.read_trace(int(trace_index), index=index), dtype=np.float64)
        trace = trace[:common:sample_step]
        trace = np.where(np.isfinite(trace), trace, 0.0)
        trace = trace - np.mean(trace)
        traces.append(trace)
    dt_values = np.asarray(index.sample_intervals_us, dtype=np.float64)[selected]
    positive = dt_values[dt_values > 0]
    dt_ms = float(np.median(positive) / 1000.0 if positive.size else 1.0) * sample_step
    return np.vstack(traces), dt_ms, [f"TRACE:{int(item) + 1}" for item in selected]


def analytic_attributes(section: np.ndarray, dt_ms: float) -> Dict[str, np.ndarray]:
    data = np.asarray(section, dtype=np.float64)
    analytic = hilbert(data, axis=1)
    envelope = np.abs(analytic)
    phase = np.angle(analytic)
    unwrapped = np.unwrap(phase, axis=1)
    dt_s = max(float(dt_ms) / 1000.0, _EPS)
    frequency = np.diff(unwrapped, axis=1, prepend=unwrapped[:, :1]) / (2.0 * np.pi * dt_s)
    nyquist = 0.5 / dt_s
    frequency = np.clip(frequency, -nyquist, nyquist)
    return {"envelope": envelope, "phase_rad": phase, "frequency_hz": frequency}


def local_coherence(section: np.ndarray, half_window: int = 2) -> np.ndarray:
    data = np.asarray(section, dtype=np.float64)
    output = np.zeros_like(data)
    for trace_index in range(data.shape[0]):
        start = max(0, trace_index - half_window)
        end = min(data.shape[0], trace_index + half_window + 1)
        output[trace_index] = sample_semblance(data[start:end], smoothing_samples=7)
    return output


def circular_phase_spread_deg(phase_rad: np.ndarray) -> np.ndarray:
    phase = np.asarray(phase_rad, dtype=np.float64)
    resultant = np.abs(np.mean(np.exp(1j * phase), axis=0))
    resultant = np.clip(resultant, _EPS, 1.0)
    return np.degrees(np.sqrt(np.maximum(0.0, -2.0 * np.log(resultant))))


def smooth_velocity(values: np.ndarray, window: int = 5) -> np.ndarray:
    data = np.asarray(values, dtype=np.float64)
    if data.size < 3:
        return data.copy()
    size = min(window if window % 2 else window + 1, data.size if data.size % 2 else data.size - 1)
    size = max(3, size)
    return median_filter(data, size=size, mode="nearest")


def velocity_smoothness_metrics(velocity_functions: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    first_changes: List[float] = []
    second_changes: List[float] = []
    for function in velocity_functions:
        velocities = np.asarray(function.get("velocities_m_s", []), dtype=np.float64)
        velocities = velocities[np.isfinite(velocities) & (velocities > 0)]
        if velocities.size < 3:
            continue
        denominator = np.maximum(np.abs(velocities[:-1]), 1.0)
        first_changes.extend((100.0 * np.abs(np.diff(velocities)) / denominator).tolist())
        median_velocity = max(float(np.median(velocities)), 1.0)
        second_changes.extend((100.0 * np.abs(np.diff(velocities, n=2)) / median_velocity).tolist())
    first = np.asarray(first_changes, dtype=np.float64)
    second = np.asarray(second_changes, dtype=np.float64)
    first_p95 = float(np.percentile(first, 95)) if first.size else 0.0
    second_median = float(np.median(second)) if second.size else 0.0
    score = float(100.0 * math.exp(-second_median / 12.0))
    return {
        "velocity_step_p95_pct": first_p95,
        "velocity_second_difference_median_pct": second_median,
        "velocity_smoothness_score_pct": score,
    }


def trace_pair_metrics(base: np.ndarray, monitor: np.ndarray, dt_ms: float, max_lag_ms: float) -> Dict[str, float]:
    length = min(base.size, monitor.size)
    if length < 8:
        return {"nrms_pct": 200.0, "predictability": 0.0, "time_shift_ms": 0.0, "amplitude_ratio": 0.0}
    base_values = np.asarray(base[:length], dtype=np.float64)
    monitor_values = np.asarray(monitor[:length], dtype=np.float64)
    base_values -= np.mean(base_values)
    monitor_values -= np.mean(monitor_values)
    max_lag_samples = max(1, int(round(max_lag_ms / max(dt_ms, _EPS))))
    lag, correlation = fft_lag_samples(monitor_values, base_values, max_lag_samples)
    shift = int(lag)
    if shift > 0:
        aligned_monitor = monitor_values[shift:]
        aligned_base = base_values[: aligned_monitor.size]
    elif shift < 0:
        aligned_base = base_values[-shift:]
        aligned_monitor = monitor_values[: aligned_base.size]
    else:
        aligned_base = base_values
        aligned_monitor = monitor_values
    if aligned_base.size < 8:
        aligned_base = base_values
        aligned_monitor = monitor_values
    rms_base = float(np.sqrt(np.mean(np.square(aligned_base))))
    rms_monitor = float(np.sqrt(np.mean(np.square(aligned_monitor))))
    nrms = 200.0 * float(np.sqrt(np.mean(np.square(aligned_monitor - aligned_base)))) / max(rms_base + rms_monitor, _EPS)
    denominator = float(np.dot(aligned_base, aligned_base) * np.dot(aligned_monitor, aligned_monitor))
    predictability = float(np.square(np.dot(aligned_base, aligned_monitor)) / max(denominator, _EPS))
    amplitude_ratio = rms_monitor / max(rms_base, _EPS)
    return {
        "nrms_pct": nrms,
        "predictability": max(0.0, min(1.0, predictability)),
        "time_shift_ms": float(lag) * float(dt_ms),
        "amplitude_ratio": amplitude_ratio,
        "correlation": correlation,
    }
