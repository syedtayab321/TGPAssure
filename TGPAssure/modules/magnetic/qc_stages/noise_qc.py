from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import DESPIKED_TOTAL_FIELD, DIURNAL_CORRECTED_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class NoiseQC(MagneticQCStage):
    key = "noise"
    display_name = "Magnetic Noise"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        channel_name, values = dataset.first_available_channel((DIURNAL_CORRECTED_FIELD, DESPIKED_TOTAL_FIELD, RAW_TOTAL_FIELD))
        groups = dataset.line_groups()
        line_noise: dict[str, float] = {}
        high_frequency: list[float] = []
        if groups:
            for line, indices in groups.items():
                line_values = values[indices]
                valid = np.isfinite(line_values)
                if np.count_nonzero(valid) < 3:
                    continue
                differences = np.diff(line_values[valid])
                noise = robust_sigma(differences) / np.sqrt(2.0)
                line_noise[line] = noise
                high_frequency.extend(differences.tolist())
                context.line_statistics.setdefault(line, {})["noise_rms_nt"] = noise
        else:
            valid = np.isfinite(values)
            high_frequency = np.diff(values[valid]).tolist() if np.count_nonzero(valid) >= 3 else []
        overall = robust_sigma(high_frequency) / np.sqrt(2.0) if high_frequency else 0.0
        worst = max(line_noise.values(), default=overall)
        findings: list[QCFinding] = []
        limit = float(self.threshold(context, "noise_rms_max_nt"))
        if overall > limit:
            findings.append(finding("MAG.NOISE.OVERALL", QCSeverity.ERROR, f"Robust high-frequency noise is {overall:.2f} nT RMS, above {limit:.2f} nT."))
        noisy_lines = [line for line, value in line_noise.items() if value > float(self.threshold(context, "rolling_noise_max_nt"))]
        if noisy_lines:
            findings.append(finding("MAG.NOISE.LINES", QCSeverity.WARNING, f"{len(noisy_lines)} lines exceed the line-noise threshold.", suggested_action="Inspect cultural noise, walking speed, sensor height and instrument status.", metadata={"lines": noisy_lines[:50]}))
        return {
            "source_channel": channel_name,
            "overall_noise_rms_nt": overall,
            "worst_line_noise_rms_nt": worst,
            "noisy_line_count": len(noisy_lines),
            "line_noise_rms_nt": line_noise,
        }, findings, "High-frequency and line-wise magnetic noise checked.", None
