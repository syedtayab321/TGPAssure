from __future__ import annotations

import math
from math import atan2, degrees, hypot
from statistics import median
from typing import Any


class ImpedanceQC:
    def __init__(self, minimum: float = 0.0, maximum: float = float("inf")) -> None:
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        if self.minimum < 0 or self.maximum < self.minimum:
            raise ValueError("Invalid impedance magnitude limits")

    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        output = []
        invalid = 0
        for row in records:
            real = float(row["impedance_real"]); imag = float(row["impedance_imag"])
            magnitude = hypot(real, imag)
            valid = math.isfinite(magnitude) and self.minimum <= magnitude <= self.maximum
            invalid += int(not valid)
            output.append({**row, "impedance_magnitude": magnitude, "impedance_valid": valid})
        return {"records": output, "invalid_count": invalid, "passed": bool(output) and invalid == 0}


class PhaseQC:
    def __init__(self, minimum_degrees: float = -180.0, maximum_degrees: float = 180.0) -> None:
        self.minimum_degrees = float(minimum_degrees)
        self.maximum_degrees = float(maximum_degrees)
        if self.maximum_degrees < self.minimum_degrees:
            raise ValueError("Invalid phase limits")

    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        output = []
        invalid = 0
        for row in records:
            phase = degrees(atan2(float(row["impedance_imag"]), float(row["impedance_real"])))
            valid = math.isfinite(phase) and self.minimum_degrees <= phase <= self.maximum_degrees
            invalid += int(not valid)
            output.append({**row, "phase_degrees": phase, "phase_valid": valid})
        return {"records": output, "invalid_count": invalid, "passed": bool(output) and invalid == 0}


class FrequencyQC:
    """Checks positive frequencies, duplicates and log-spacing consistency."""
    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        frequencies = [float(row["frequency_hz"]) for row in records]
        positive = [value for value in frequencies if math.isfinite(value) and value > 0]
        unique = sorted(set(positive))
        duplicates = len(positive) - len(unique)
        log_steps = [math.log10(b) - math.log10(a) for a, b in zip(unique, unique[1:]) if a > 0 and b > 0]
        median_log_step = median(log_steps) if log_steps else None
        return {
            "record_count": len(records), "unique_frequency_count": len(unique),
            "duplicate_frequency_count": duplicates, "minimum_frequency_hz": min(unique) if unique else None,
            "maximum_frequency_hz": max(unique) if unique else None, "median_log10_step": median_log_step,
            "passed": len(positive) == len(records) and duplicates == 0,
        }


class EmQcPipeline:
    def __init__(self, impedance: ImpedanceQC | None = None, phase: PhaseQC | None = None) -> None:
        self.impedance = impedance or ImpedanceQC()
        self.phase = phase or PhaseQC()
        self.frequency = FrequencyQC()

    def run(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            raise ValueError("No EM records supplied")
        impedance = self.impedance.apply(records)
        phase = self.phase.apply(impedance["records"])
        frequency = self.frequency.apply(phase["records"])
        passed = bool(impedance["passed"] and phase["passed"] and frequency["passed"])
        return {"records": phase["records"], "impedance": impedance, "phase": phase, "frequency": frequency, "passed": passed}
