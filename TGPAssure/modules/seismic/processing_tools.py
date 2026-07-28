from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class FirstBreakPick:
    trace_index: int
    sample_index: int
    time_ms: float
    confidence: float


class FirstBreakAutoPicker:
    def __init__(self, sta_samples: int = 10, lta_samples: int = 100, threshold: float = 3.0) -> None:
        if sta_samples <= 0 or lta_samples <= sta_samples or threshold <= 0:
            raise ValueError('Require 0 < sta_samples < lta_samples and a positive threshold')
        self.sta_samples = sta_samples
        self.lta_samples = lta_samples
        self.threshold = threshold

    def pick(self, traces: np.ndarray, sample_interval_ms: float) -> list[FirstBreakPick]:
        data = np.asarray(traces, dtype=float)
        if data.ndim == 1:
            data = data[np.newaxis, :]
        if data.ndim != 2 or data.shape[1] < self.lta_samples:
            raise ValueError('Traces must be a two-dimensional array with at least lta_samples samples')
        energy = data * data
        picks = []
        for trace_index, trace_energy in enumerate(energy):
            sta = np.convolve(trace_energy, np.ones(self.sta_samples) / self.sta_samples, mode='same')
            lta = np.convolve(trace_energy, np.ones(self.lta_samples) / self.lta_samples, mode='same')
            ratio = sta / np.maximum(lta, np.finfo(float).eps)
            candidates = np.flatnonzero(ratio[self.lta_samples:] >= self.threshold)
            sample_index = int(candidates[0] + self.lta_samples) if candidates.size else int(np.argmax(ratio))
            picks.append(FirstBreakPick(trace_index, sample_index, sample_index * sample_interval_ms, float(ratio[sample_index])))
        return picks


class TraceFilter:
    def apply(self, trace: np.ndarray, sample_interval_ms: float, kind: str, low_hz: float | None = None, high_hz: float | None = None) -> np.ndarray:
        values = np.asarray(trace, dtype=float)
        if values.ndim != 1 or sample_interval_ms <= 0:
            raise ValueError('Trace must be one-dimensional and sample_interval_ms must be positive')
        frequencies = np.fft.rfftfreq(values.size, d=sample_interval_ms / 1000.0)
        spectrum = np.fft.rfft(values)
        if kind == 'lowpass':
            if high_hz is None:
                raise ValueError('high_hz is required for lowpass')
            mask = frequencies <= high_hz
        elif kind == 'highpass':
            if low_hz is None:
                raise ValueError('low_hz is required for highpass')
            mask = frequencies >= low_hz
        elif kind == 'bandpass':
            if low_hz is None or high_hz is None or low_hz >= high_hz:
                raise ValueError('bandpass requires low_hz < high_hz')
            mask = (frequencies >= low_hz) & (frequencies <= high_hz)
        elif kind == 'notch':
            if low_hz is None or high_hz is None or low_hz >= high_hz:
                raise ValueError('notch requires low_hz < high_hz')
            mask = (frequencies < low_hz) | (frequencies > high_hz)
        else:
            raise ValueError(f'Unsupported filter kind: {kind}')
        return np.fft.irfft(spectrum * mask, n=values.size)


class AreaAnalyzer:
    def analyze(self, traces: np.ndarray, sample_interval_ms: float) -> dict[str, float | np.ndarray]:
        values = np.asarray(traces, dtype=float)
        if values.size == 0 or sample_interval_ms <= 0:
            raise ValueError('Area must contain samples and have a positive sample interval')
        flattened = values.ravel()
        spectrum = np.abs(np.fft.rfft(flattened))
        frequencies = np.fft.rfftfreq(flattened.size, sample_interval_ms / 1000.0)
        dominant_index = int(np.argmax(spectrum[1:]) + 1) if spectrum.size > 1 else 0
        return {'rms': float(np.sqrt(np.mean(flattened ** 2))), 'dominant_frequency_hz': float(frequencies[dominant_index]), 'frequencies_hz': frequencies, 'amplitudes': spectrum}


class RefractionLayerAnalysis:
    def fit(self, offsets_m: Iterable[float], times_ms: Iterable[float]) -> dict[str, float]:
        offsets = np.asarray(list(offsets_m), dtype=float)
        times = np.asarray(list(times_ms), dtype=float) / 1000.0
        if offsets.size < 2 or offsets.size != times.size:
            raise ValueError('At least two paired offset and time values are required')
        slope, intercept = np.polyfit(offsets, times, 1)
        if slope <= 0:
            raise ValueError('Travel-time slope must be positive')
        return {'velocity_m_s': float(1.0 / slope), 'intercept_time_ms': float(intercept * 1000.0), 'slope_s_m': float(slope)}
