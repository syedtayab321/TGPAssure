from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import VERTICAL_GRADIENT
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class GradientQC(MagneticQCStage):
    key = "gradient"
    display_name = "Magnetic Gradient"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        if VERTICAL_GRADIENT in dataset.channels:
            gradient = dataset.channel(VERTICAL_GRADIENT)
            separation = dataset.metadata.get("sensor_separation_m")
        elif "sensor_1_raw" in dataset.channels and "sensor_2_raw" in dataset.channels:
            separation = float(dataset.metadata.get("sensor_separation_m", 0.0) or 0.0)
            if separation <= 0:
                item = finding("MAG.GRADIENT.SEPARATION", QCSeverity.ERROR, "Dual-sensor data are available but sensor separation is not defined.", suggested_action="Enter the verified sensor separation in metres.")
                return {"sensor_separation_m": separation}, [item], "Gradient cannot be validated.", None
            gradient = (dataset.channel("sensor_1_raw") - dataset.channel("sensor_2_raw")) / separation
            dataset.add_derived_channel(VERTICAL_GRADIENT, gradient, parent_channel="sensor_1_raw,sensor_2_raw", operation="dual_sensor_gradient", parameters={"sensor_separation_m": separation})
        else:
            return self.skipped("The dataset contains only one magnetic sensor.")
        valid = np.isfinite(gradient)
        noise = robust_sigma(np.diff(gradient[valid])) / np.sqrt(2.0) if np.count_nonzero(valid) >= 3 else 0.0
        findings: list[QCFinding] = []
        if noise > float(self.threshold(context, "gradient_noise_max_nt_m")):
            findings.append(finding("MAG.GRADIENT.NOISE", QCSeverity.WARNING, f"Gradient noise is {noise:.2f} nT/m.", suggested_action="Check sensor separation, mounting, vibration and independent sensor spikes."))
        return {
            "sensor_separation_m": separation,
            "valid_gradient_pct": 100.0 * np.count_nonzero(valid) / gradient.size,
            "gradient_min_nt_m": float(np.nanmin(gradient)) if np.any(valid) else None,
            "gradient_max_nt_m": float(np.nanmax(gradient)) if np.any(valid) else None,
            "gradient_noise_nt_m": noise,
        }, findings, "Dual-sensor gradient range and noise checked.", None
