from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding


class PlatformQC(MagneticQCStage):
    key = "platform"
    display_name = "Survey Platform"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        findings: list[QCFinding] = []
        metrics: dict[str, Any] = {"survey_type": dataset.survey_type.value}
        if dataset.survey_type.value == "ground":
            if "speed" not in dataset.channels:
                return self.skipped("Ground speed was evaluated from coordinates; no additional platform channels are available.", metrics)
            speed = dataset.channel("speed")
            limit = float(self.threshold(context, "ground_speed_max_m_s"))
            exceed = np.isfinite(speed) & (speed > limit)
            metrics.update({"maximum_speed_m_s": float(np.nanmax(speed)) if np.any(np.isfinite(speed)) else None, "speed_exceedance_count": int(np.count_nonzero(exceed))})
            if np.any(exceed):
                findings.append(finding("MAG.PLATFORM.SPEED", QCSeverity.WARNING, f"{np.count_nonzero(exceed)} records exceed the configured ground speed."))
            return metrics, findings, "Ground platform speed checked.", None
        if "terrain_clearance" in dataset.channels:
            clearance = dataset.channel("terrain_clearance")
            low = np.isfinite(clearance) & (clearance < float(self.threshold(context, "terrain_clearance_min_m")))
            metrics["minimum_terrain_clearance_m"] = float(np.nanmin(clearance)) if np.any(np.isfinite(clearance)) else None
            if np.any(low):
                findings.append(finding("MAG.PLATFORM.CLEARANCE", QCSeverity.ERROR, f"{np.count_nonzero(low)} records are below minimum terrain clearance."))
        else:
            findings.append(finding("MAG.PLATFORM.CLEARANCE_MISSING", QCSeverity.WARNING, "Terrain-clearance data are not available for this moving platform."))
        for name in ("heading", "roll", "pitch", "yaw", "speed"):
            if name in dataset.channels:
                values = dataset.channel(name)
                metrics[f"{name}_minimum"] = float(np.nanmin(values)) if np.any(np.isfinite(values)) else None
                metrics[f"{name}_maximum"] = float(np.nanmax(values)) if np.any(np.isfinite(values)) else None
        return metrics, findings, "Altitude, clearance and available platform attitude channels checked.", None
