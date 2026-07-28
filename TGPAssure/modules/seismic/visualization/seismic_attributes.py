from __future__ import annotations

"""Numerically stable seismic attributes for interactive QC and interpretation.

The functions in this module are intentionally independent of the GUI.  Input
sections use TGPAssure's standard ``(samples, traces)`` orientation and may
contain NaN padding for variable-length SEG-Y traces.  Missing data are kept as
missing data rather than converted into artificial zero-amplitude events.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import hilbert


ATTRIBUTE_NAMES: Final[dict[str, str]] = {
    "amplitude": "Amplitude",
    "envelope": "Reflection Strength / Envelope",
    "instantaneous_phase": "Instantaneous Phase",
    "instantaneous_frequency": "Instantaneous Frequency",
    "rms_amplitude": "RMS Amplitude",
    "semblance": "Local Semblance / Coherence",
    "sweetness": "Sweetness",
}


@dataclass(frozen=True, slots=True)
class AttributeParameters:
    rms_window_ms: float = 40.0
    coherence_window_ms: float = 32.0
    coherence_trace_radius: int = 2
    minimum_frequency_hz: float = 1.0
    maximum_frequency_hz: float | None = None


def _as_section(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError("Seismic attribute input must be a 2-D (samples, traces) array")
    return arr


def _window_samples(window_ms: float, sample_interval_ms: float, minimum: int = 1) -> int:
    if not np.isfinite(sample_interval_ms) or sample_interval_ms <= 0:
        raise ValueError("Sample interval must be a positive finite value")
    if not np.isfinite(window_ms) or window_ms <= 0:
        return minimum
    samples = max(minimum, int(round(float(window_ms) / float(sample_interval_ms))))
    # Odd windows are symmetric around the interpreted sample.
    return samples if samples % 2 else samples + 1


def _interpolate_nan_traces(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fill internal NaNs only for transforms that mathematically require continuity.

    The returned validity mask is used to restore missing samples in every
    derived attribute. Edge gaps are extended from the nearest finite sample
    for numerical stability, then masked back to NaN after the transform.
    """
    arr = _as_section(data)
    valid = np.isfinite(arr)
    filled = np.zeros_like(arr, dtype=np.float64)
    sample_axis = np.arange(arr.shape[0], dtype=np.float64)
    for column in range(arr.shape[1]):
        mask = valid[:, column]
        if not np.any(mask):
            continue
        values = arr[mask, column]
        positions = sample_axis[mask]
        if positions.size == 1:
            filled[:, column] = values[0]
        else:
            filled[:, column] = np.interp(sample_axis, positions, values)
    return filled, valid


def analytic_signal(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    filled, valid = _interpolate_nan_traces(data)
    if filled.size == 0:
        return filled.astype(np.complex128), valid
    analytic = hilbert(filled, axis=0)
    return analytic, valid


def envelope(data: np.ndarray) -> np.ndarray:
    analytic, valid = analytic_signal(data)
    result = np.abs(analytic)
    result[~valid] = np.nan
    return result.astype(np.float32)


def instantaneous_phase(data: np.ndarray, *, degrees: bool = True) -> np.ndarray:
    analytic, valid = analytic_signal(data)
    phase = np.angle(analytic)
    if degrees:
        phase = np.degrees(phase)
    phase[~valid] = np.nan
    return phase.astype(np.float32)


def instantaneous_frequency(
    data: np.ndarray,
    sample_interval_ms: float,
    *,
    maximum_frequency_hz: float | None = None,
) -> np.ndarray:
    analytic, valid = analytic_signal(data)
    if analytic.shape[0] == 0:
        return np.empty_like(np.asarray(data), dtype=np.float32)
    dt_s = float(sample_interval_ms) / 1000.0
    if not np.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("Sample interval must be positive")
    unwrapped = np.unwrap(np.angle(analytic), axis=0)
    # Central differences via gradient avoid the one-sample shift produced by diff.
    frequency = np.gradient(unwrapped, dt_s, axis=0) / (2.0 * np.pi)
    envelope = np.abs(analytic)
    trace_peak = np.nanmax(envelope, axis=0, keepdims=True)
    stable_phase = envelope > np.maximum(trace_peak * 1.0e-6, np.finfo(np.float64).eps)
    nyquist = 0.5 / dt_s
    upper = nyquist if maximum_frequency_hz is None else min(float(maximum_frequency_hz), nyquist)
    # Instantaneous frequency is undefined at envelope nulls and physically bounded
    # by the sampled Nyquist interval. Keep negative values (they can be meaningful
    # for local phase reversals) but reject unstable/null and aliased estimates.
    frequency[(frequency < -upper) | (frequency > upper) | ~stable_phase] = np.nan
    frequency[~valid] = np.nan
    return frequency.astype(np.float32)


def rms_amplitude(data: np.ndarray, sample_interval_ms: float, window_ms: float = 40.0) -> np.ndarray:
    arr = _as_section(data)
    valid = np.isfinite(arr)
    width = _window_samples(window_ms, sample_interval_ms, minimum=1)
    values = np.where(valid, arr, 0.0)
    weights = uniform_filter1d(valid.astype(np.float64), size=width, axis=0, mode="nearest")
    mean_square = uniform_filter1d(values * values, size=width, axis=0, mode="nearest")
    result = np.sqrt(np.divide(mean_square, weights, out=np.full_like(mean_square, np.nan), where=weights > 1e-12))
    result[~valid] = np.nan
    return result.astype(np.float32)


def local_semblance(
    data: np.ndarray,
    sample_interval_ms: float,
    *,
    window_ms: float = 32.0,
    trace_radius: int = 2,
) -> np.ndarray:
    """Compute a bounded local semblance attribute in [0, 1].

    For each sample, traces inside the lateral aperture are stacked. Semblance
    is the time-windowed ratio ``sum(stack^2) / sum(N * energy)``. This is a
    standard coherence measure: perfectly aligned neighbouring events approach
    1, while incoherent/noisy events approach 0.
    """
    arr = _as_section(data)
    if arr.size == 0:
        return arr.astype(np.float32)
    radius = max(0, int(trace_radius))
    lateral = 2 * radius + 1
    temporal = _window_samples(window_ms, sample_interval_ms, minimum=1)
    valid = np.isfinite(arr)
    values = np.where(valid, arr, 0.0)

    # uniform_filter1d returns a mean; multiply by aperture width to recover sums.
    lateral_sum = uniform_filter1d(values, size=lateral, axis=1, mode="constant", cval=0.0) * lateral
    lateral_energy = uniform_filter1d(values * values, size=lateral, axis=1, mode="constant", cval=0.0) * lateral
    lateral_count = uniform_filter1d(valid.astype(np.float64), size=lateral, axis=1, mode="constant", cval=0.0) * lateral

    numerator = uniform_filter1d(lateral_sum * lateral_sum, size=temporal, axis=0, mode="constant", cval=0.0)
    denominator = uniform_filter1d(lateral_count * lateral_energy, size=temporal, axis=0, mode="constant", cval=0.0)
    result = np.divide(numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 1e-20)
    result = np.clip(result, 0.0, 1.0)
    result[~valid] = np.nan
    return result.astype(np.float32)


def sweetness(
    data: np.ndarray,
    sample_interval_ms: float,
    *,
    minimum_frequency_hz: float = 1.0,
    maximum_frequency_hz: float | None = None,
) -> np.ndarray:
    """Compute sweetness = envelope / sqrt(|instantaneous frequency|).

    A small configurable frequency floor prevents singularities around phase
    reversals and envelope nulls. The output retains NaNs from missing samples.
    """
    env = envelope(data).astype(np.float64)
    freq = instantaneous_frequency(
        data,
        sample_interval_ms,
        maximum_frequency_hz=maximum_frequency_hz,
    ).astype(np.float64)
    floor = max(float(minimum_frequency_hz), np.finfo(np.float64).eps)
    denominator = np.sqrt(np.maximum(np.abs(freq), floor))
    result = np.divide(env, denominator, out=np.full_like(env, np.nan), where=np.isfinite(denominator))
    return result.astype(np.float32)


def compute_attribute(
    data: np.ndarray,
    sample_interval_ms: float,
    attribute: str,
    parameters: AttributeParameters | None = None,
) -> np.ndarray:
    """Calculate a named seismic attribute for display or QC review."""
    key = str(attribute).strip().lower()
    params = parameters or AttributeParameters()
    if key == "amplitude":
        return np.asarray(data, dtype=np.float32).copy()
    if key == "envelope":
        return envelope(data)
    if key == "instantaneous_phase":
        return instantaneous_phase(data)
    if key == "instantaneous_frequency":
        return instantaneous_frequency(data, sample_interval_ms, maximum_frequency_hz=params.maximum_frequency_hz)
    if key == "rms_amplitude":
        return rms_amplitude(data, sample_interval_ms, params.rms_window_ms)
    if key == "semblance":
        return local_semblance(
            data,
            sample_interval_ms,
            window_ms=params.coherence_window_ms,
            trace_radius=params.coherence_trace_radius,
        )
    if key == "sweetness":
        return sweetness(
            data,
            sample_interval_ms,
            minimum_frequency_hz=params.minimum_frequency_hz,
            maximum_frequency_hz=params.maximum_frequency_hz,
        )
    raise ValueError(f"Unsupported seismic attribute: {attribute}")



def volume_semblance(
    volume: np.ndarray,
    sample_interval_ms: float,
    *,
    window_ms: float = 32.0,
    spatial_radius: int = 1,
) -> np.ndarray:
    """Compute 3-D local semblance on an ``(inline, crossline, samples)`` volume.

    The numerator is the time-windowed energy of the spatial stack and the
    denominator is the corresponding trace-count-weighted spatial energy.
    Missing bins are excluded from both terms and remain NaN in the result.
    """
    arr = np.asarray(volume, dtype=np.float64)
    if arr.ndim != 3:
        raise ValueError("Seismic volume attribute input must be 3-D (inline, crossline, samples)")
    if arr.size == 0:
        return arr.astype(np.float32)
    radius = max(0, int(spatial_radius))
    aperture = 2 * radius + 1
    temporal = _window_samples(window_ms, sample_interval_ms, minimum=1)
    valid = np.isfinite(arr)
    values = np.where(valid, arr, 0.0)

    def spatial_sum(data: np.ndarray) -> np.ndarray:
        first = uniform_filter1d(data, size=aperture, axis=0, mode="constant", cval=0.0) * aperture
        return uniform_filter1d(first, size=aperture, axis=1, mode="constant", cval=0.0) * aperture

    stacked = spatial_sum(values)
    energy = spatial_sum(values * values)
    count = spatial_sum(valid.astype(np.float64))
    numerator = uniform_filter1d(stacked * stacked, size=temporal, axis=2, mode="constant", cval=0.0)
    denominator = uniform_filter1d(count * energy, size=temporal, axis=2, mode="constant", cval=0.0)
    result = np.divide(numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 1e-20)
    result = np.clip(result, 0.0, 1.0)
    result[~valid] = np.nan
    return result.astype(np.float32)


def compute_volume_attribute(
    volume: np.ndarray,
    sample_interval_ms: float,
    attribute: str,
    parameters: AttributeParameters | None = None,
) -> np.ndarray:
    """Calculate a named attribute on a seismic volume without changing geometry.

    Single-trace analytic attributes are calculated independently along the time
    axis. Local semblance uses a true inline/crossline spatial aperture instead
    of flattening adjacent rows into an artificial 2-D trace sequence.
    """
    arr = np.asarray(volume, dtype=np.float32)
    if arr.ndim != 3:
        raise ValueError("Seismic volume attribute input must be 3-D (inline, crossline, samples)")
    key = str(attribute).strip().lower()
    params = parameters or AttributeParameters()
    if key == "amplitude":
        return arr.copy()
    if key == "semblance":
        return volume_semblance(
            arr,
            sample_interval_ms,
            window_ms=params.coherence_window_ms,
            spatial_radius=params.coherence_trace_radius,
        )
    inline_count, crossline_count, sample_count = arr.shape
    traces = arr.transpose(2, 0, 1).reshape(sample_count, inline_count * crossline_count)
    derived = compute_attribute(traces, sample_interval_ms, key, params)
    return derived.reshape(sample_count, inline_count, crossline_count).transpose(1, 2, 0).astype(np.float32, copy=False)

def attribute_display_range(data: np.ndarray, attribute: str, percentile: float = 99.0) -> tuple[float, float]:
    """Return robust colour limits appropriate to the attribute's physical range."""
    values = np.asarray(data, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return -1.0, 1.0
    key = str(attribute).lower()
    p = float(np.clip(percentile, 50.0, 100.0))
    if key == "instantaneous_phase":
        return -180.0, 180.0
    if key == "semblance":
        return 0.0, 1.0
    if key in {"envelope", "rms_amplitude", "sweetness"}:
        high = float(np.percentile(finite, p))
        return 0.0, high if high > 1e-12 else 1.0
    limit = float(np.percentile(np.abs(finite), p))
    return (-limit, limit) if limit > 1e-12 else (-1.0, 1.0)
