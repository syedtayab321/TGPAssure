from __future__ import annotations

from typing import Iterable

import numpy as np
from scipy.ndimage import uniform_filter1d

from modules.seismic.visualization.models import GainSettings, NoiseResult, QcTraceFlag, SpectrumResult


def apply_gain(amplitudes: np.ndarray, sample_interval_ms: float, settings: GainSettings) -> np.ndarray:
    """Apply display-only gain while preserving missing SEG-Y coverage as NaN."""
    data = np.asarray(amplitudes, dtype=np.float32).copy()
    if data.ndim != 2 or data.size == 0:
        return data
    valid = np.isfinite(data)
    work = np.where(valid, data, 0.0).astype(np.float32, copy=False)
    if settings.normalize_traces:
        scale = np.max(np.abs(work), axis=0, keepdims=True)
        scale[scale <= np.finfo(np.float32).eps] = 1.0
        work /= scale
    if settings.agc_enabled:
        window_samples = max(3, int(round(float(settings.agc_window_ms) / max(sample_interval_ms, 1e-6))))
        if window_samples % 2 == 0:
            window_samples += 1
        weights = uniform_filter1d(valid.astype(np.float32), size=window_samples, axis=0, mode="nearest")
        energy = uniform_filter1d(work * work, size=window_samples, axis=0, mode="nearest")
        local_mean_square = np.divide(
            energy, weights, out=np.zeros_like(energy), where=weights > np.finfo(np.float32).eps
        )
        work /= np.sqrt(np.maximum(local_mean_square, 1e-12))
    work *= float(settings.scalar)
    percentile = float(np.clip(settings.clip_percentile, 50.0, 100.0))
    finite = np.abs(work[valid])
    clip_value = float(np.percentile(finite, percentile)) if finite.size else 0.0
    if clip_value > 0.0:
        np.clip(work, -clip_value, clip_value, out=work)
    work[~valid] = np.nan
    return work


def robust_scale(amplitudes: np.ndarray, percentile: float = 99.0) -> float:
    data = np.asarray(amplitudes, dtype=np.float32)
    if data.size == 0:
        return 1.0
    finite = np.abs(data[np.isfinite(data)])
    if finite.size == 0:
        return 1.0
    maximum_samples = 2_000_000
    if finite.size > maximum_samples:
        step = max(1, finite.size // maximum_samples)
        finite = finite[::step]
    value = float(np.percentile(finite, np.clip(percentile, 50.0, 100.0)))
    return value if value > np.finfo(np.float32).eps else 1.0


def detect_bad_traces(
    amplitudes: np.ndarray,
    trace_indices: Iterable[int],
    low_rms_ratio: float = 0.08,
    high_rms_ratio: float = 8.0,
    zero_fraction_limit: float = 0.98,
    clipping_fraction_limit: float = 0.02,
    spike_score_limit: float = 20.0,
) -> list[QcTraceFlag]:
    """Flag trace-level amplitude defects without treating NaN padding as real zeros."""
    data = np.asarray(amplitudes, dtype=np.float32)
    if data.ndim != 2 or data.size == 0:
        return []
    indices = np.asarray(list(trace_indices), dtype=np.int64)
    if indices.size != data.shape[1]:
        raise ValueError("Trace index count must match the section trace count")
    valid = np.isfinite(data)
    valid_count = np.sum(valid, axis=0)
    safe_count = np.maximum(valid_count, 1)
    work = np.where(valid, data, 0.0)
    absolute = np.abs(work)
    rms = np.sqrt(np.sum(work * work, axis=0) / safe_count)
    peak = np.max(absolute, axis=0)
    zero_fraction = np.sum(valid & (absolute <= 1e-12), axis=0) / safe_count
    finite_peaks = peak[(valid_count > 0) & np.isfinite(peak)]
    global_peak = max(float(np.percentile(finite_peaks, 95.0)), 1e-12) if finite_peaks.size else 1e-12
    clipping_fraction = np.sum(valid & (absolute >= global_peak * 0.999), axis=0) / safe_count
    derivative = np.diff(work, axis=0, prepend=work[:1, :])
    derivative_valid = valid & np.vstack((valid[:1, :], valid[:-1, :]))
    abs_derivative = np.where(derivative_valid, np.abs(derivative), np.nan)
    median_derivative = np.nanmedian(abs_derivative, axis=0)
    max_derivative = np.nanmax(abs_derivative, axis=0)
    spike_score = max_derivative / np.maximum(np.nan_to_num(median_derivative, nan=0.0), 1e-12)
    positive_rms = rms[(rms > 0) & (valid_count > 0)]
    median_rms = float(np.median(positive_rms)) if positive_rms.size else 0.0
    flags: list[QcTraceFlag] = []
    for column, trace_index in enumerate(indices):
        reasons: list[str] = []
        severity = "warning"
        if valid_count[column] == 0:
            reasons.append("no valid samples in display window")
            severity = "error"
        elif zero_fraction[column] >= zero_fraction_limit:
            reasons.append("dead or near-zero trace")
            severity = "error"
        if median_rms > 0 and rms[column] < median_rms * low_rms_ratio:
            reasons.append("abnormally low RMS")
        if median_rms > 0 and rms[column] > median_rms * high_rms_ratio:
            reasons.append("abnormally high RMS")
            severity = "error"
        if clipping_fraction[column] >= clipping_fraction_limit:
            reasons.append("possible clipping")
        if np.isfinite(spike_score[column]) and spike_score[column] >= spike_score_limit:
            reasons.append("impulsive spikes")
        if reasons:
            flags.append(
                QcTraceFlag(
                    trace_index=int(trace_index),
                    severity=severity,
                    reason=", ".join(reasons),
                    rms=float(rms[column]),
                    peak=float(peak[column]),
                    zero_fraction=float(zero_fraction[column]),
                    clipping_fraction=float(clipping_fraction[column]),
                    spike_score=float(np.nan_to_num(spike_score[column], nan=0.0, posinf=0.0)),
                )
            )
    return flags


def calculate_spectrum(amplitudes: np.ndarray, sample_interval_ms: float) -> SpectrumResult:
    data = np.asarray(amplitudes, dtype=np.float32)
    if data.ndim != 2 or data.shape[0] < 4 or data.shape[1] == 0:
        empty = np.empty(0, dtype=np.float32)
        return SpectrumResult(empty, empty, empty)
    window = np.hanning(data.shape[0]).astype(np.float32)[:, None]
    work = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    spectra = np.abs(np.fft.rfft(work * window, axis=0)).astype(np.float32)
    frequency = np.fft.rfftfreq(data.shape[0], d=max(sample_interval_ms, 1e-6) / 1000.0).astype(np.float32)
    return SpectrumResult(
        frequency_hz=frequency,
        mean_amplitude=np.mean(spectra, axis=1).astype(np.float32),
        median_amplitude=np.median(spectra, axis=1).astype(np.float32),
    )


def calculate_noise_metrics(
    amplitudes: np.ndarray,
    trace_indices: Iterable[int],
    sample_interval_ms: float,
) -> NoiseResult:
    data = np.asarray(amplitudes, dtype=np.float32)
    indices = np.asarray(list(trace_indices), dtype=np.int64)
    if data.ndim != 2 or data.shape[1] == 0:
        empty = np.empty(0, dtype=np.float32)
        return NoiseResult(indices, empty, empty, empty)
    valid = np.isfinite(data)
    work = np.where(valid, data, 0.0)
    counts = np.maximum(np.sum(valid, axis=0), 1)
    rms = np.sqrt(np.sum(work * work, axis=0) / counts).astype(np.float32)
    spectra = np.abs(np.fft.rfft(work, axis=0)).astype(np.float32)
    frequency = np.fft.rfftfreq(data.shape[0], d=max(sample_interval_ms, 1e-6) / 1000.0)
    nyquist = float(frequency[-1]) if frequency.size else 0.0
    high_mask = frequency >= nyquist * 0.6
    total_energy = np.sum(spectra * spectra, axis=0)
    high_energy = np.sum((spectra[high_mask, :] ** 2), axis=0) if np.any(high_mask) else np.zeros(data.shape[1])
    high_ratio = (high_energy / np.maximum(total_energy, 1e-12)).astype(np.float32)
    if data.shape[1] > 1:
        normalized = work / np.maximum(np.sqrt(np.sum(work * work, axis=0, keepdims=True)), 1e-12)
        neighbor_coherence = np.sum(normalized[:, 1:] * normalized[:, :-1], axis=0)
        incoherence = np.ones(data.shape[1], dtype=np.float32)
        incoherence[0] = 1.0 - float(neighbor_coherence[0])
        incoherence[-1] = 1.0 - float(neighbor_coherence[-1])
        if data.shape[1] > 2:
            incoherence[1:-1] = 1.0 - 0.5 * (neighbor_coherence[:-1] + neighbor_coherence[1:])
        incoherence = np.clip(incoherence, 0.0, 2.0)
    else:
        incoherence = np.zeros(1, dtype=np.float32)
    return NoiseResult(
        trace_indices=indices.astype(np.int64),
        rms=rms,
        high_frequency_ratio=high_ratio,
        incoherence=incoherence.astype(np.float32),
    )


def snap_sample(amplitudes: np.ndarray, column: int, sample: int, radius: int = 8) -> int:
    data = np.asarray(amplitudes, dtype=np.float32)
    if data.ndim != 2 or data.size == 0:
        return int(sample)
    column = max(0, min(int(column), data.shape[1] - 1))
    sample = max(0, min(int(sample), data.shape[0] - 1))
    start = max(0, sample - max(1, int(radius)))
    stop = min(data.shape[0], sample + max(1, int(radius)) + 1)
    local = np.abs(data[start:stop, column])
    if local.size == 0:
        return sample
    return int(start + int(np.argmax(local)))


def normalized_rgba_volume(
    amplitudes: np.ndarray,
    opacity: float = 0.35,
    clip_percentile: float = 98.5,
    transparency_threshold: float = 0.035,
    opacity_gamma: float = 0.72,
) -> np.ndarray:
    """Build an RGBA seismic volume using a tunable amplitude transfer function.

    ``clip_percentile`` controls robust amplitude scaling. ``transparency_threshold``
    suppresses low-amplitude voxels as a fraction of the robust scale, while
    ``opacity_gamma`` shapes how quickly stronger reflectors become opaque.
    """
    raw = np.asarray(amplitudes, dtype=np.float32)
    if raw.ndim != 3:
        raise ValueError("Volume data must be a 3D array")
    valid = np.isfinite(raw)
    scale = robust_scale(raw, float(np.clip(clip_percentile, 50.0, 100.0)))
    data = np.where(valid, raw, 0.0)
    normalized = np.clip(data / scale, -1.0, 1.0)
    magnitude = np.abs(normalized)
    rgba = np.empty(data.shape + (4,), dtype=np.ubyte)
    positive = normalized >= 0
    rgba[..., 0] = np.where(positive, 250, 35).astype(np.ubyte)
    rgba[..., 1] = np.where(positive, 245 * (1.0 - magnitude), 145 * (1.0 - magnitude)).astype(np.ubyte)
    rgba[..., 2] = np.where(positive, 245 * (1.0 - magnitude), 250).astype(np.ubyte)
    threshold = float(np.clip(transparency_threshold, 0.0, 0.95))
    visible = np.clip((magnitude - threshold) / max(1.0 - threshold, 1e-6), 0.0, 1.0)
    visible = np.power(visible, max(0.05, float(opacity_gamma)))
    alpha = np.clip(visible * float(np.clip(opacity, 0.01, 1.0)) * 255.0, 0.0, 255.0)
    rgba[..., 3] = np.where(valid, alpha, 0.0).astype(np.ubyte)
    return rgba

