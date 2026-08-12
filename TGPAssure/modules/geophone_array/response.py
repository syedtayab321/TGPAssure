from __future__ import annotations

import math
from dataclasses import dataclass

from .models import GeophoneArrayModel


@dataclass(slots=True)
class ResponseCurve:
    x_values: list[float]
    y_values: list[float]
    projected_length: float


def calculate_response(model: GeophoneArrayModel, azimuth_deg: float, max_ratio: float = 12.0, samples: int = 800) -> ResponseCurve:
    """Calculate normalized geophone-array response versus array-length / wavelength.

    The curve uses the standard array-factor magnitude: each element is projected
    onto the selected azimuth and summed as a unit phasor. The output is normalized
    to 1.0, matching the GAR-style response chart scale.
    """
    points = model.points
    if not points:
        xs = [i * max_ratio / max(samples - 1, 1) for i in range(samples)]
        return ResponseCurve(xs, [0.0] * len(xs), 0.0)

    theta = math.radians(float(azimuth_deg))
    ux, uy = math.cos(theta), math.sin(theta)
    projections = [p.x * ux + p.y * uy for p in points]
    centre = sum(projections) / len(projections)
    projections = [p - centre for p in projections]
    projected_length = max(projections) - min(projections) if len(projections) > 1 else 1.0
    if projected_length <= 1e-9:
        projected_length = max(model.array_length, 1.0)
    normalized = [p / projected_length for p in projections]
    x_values: list[float] = []
    y_values: list[float] = []
    for i in range(max(samples, 2)):
        ratio = i * float(max_ratio) / float(max(samples, 2) - 1)
        real = 0.0
        imag = 0.0
        for pos in normalized:
            phase = 2.0 * math.pi * ratio * pos
            real += math.cos(phase)
            imag += math.sin(phase)
        amp = math.hypot(real, imag) / len(normalized)
        x_values.append(ratio)
        y_values.append(max(0.0, min(1.0, amp)))
    return ResponseCurve(x_values, y_values, projected_length)


def wavenumber_to_frequency(wavenumber_ratio: float, velocity: float, array_length: float) -> float:
    if array_length <= 0:
        return 0.0
    return float(wavenumber_ratio) * float(velocity) / float(array_length)


def frequency_to_velocity(wavenumber_ratio: float, frequency: float, array_length: float) -> float:
    if wavenumber_ratio <= 0:
        return 0.0
    return float(frequency) * float(array_length) / float(wavenumber_ratio)
