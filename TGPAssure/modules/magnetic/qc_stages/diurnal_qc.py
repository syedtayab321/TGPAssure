from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import BASE_TOTAL_FIELD, DIURNAL_CORRECTED_FIELD, DIURNAL_CORRECTION
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class DiurnalQC(MagneticQCStage):
    key = "diurnal"
    display_name = "Diurnal Correction"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        rover = context.rover_dataset
        findings: list[QCFinding] = []
        if DIURNAL_CORRECTION not in rover.channels:
            if context.base_dataset is None:
                return self.skipped("No diurnal-correction channel or base dataset is available.")
            findings.append(finding("MAG.DIURNAL.NOT_APPLIED", QCSeverity.WARNING, "A valid base dataset is loaded but diurnal correction has not been applied.", suggested_action="Run Magnetic Processing → Diurnal Correction, then repeat processed-data QC."))
            return {"correction_available": False}, findings, "Diurnal correction is pending.", None
        correction = rover.channel(DIURNAL_CORRECTION)
        finite = np.isfinite(correction)
        maximum = float(np.nanmax(np.abs(correction))) if np.any(finite) else 0.0
        if maximum > float(self.threshold(context, "diurnal_correction_max_nt")):
            findings.append(finding("MAG.DIURNAL.MAGNITUDE", QCSeverity.ERROR, f"Maximum absolute diurnal correction is {maximum:.1f} nT.", suggested_action="Review storm periods, time synchronization and base station location."))
        residual = None
        if DIURNAL_CORRECTED_FIELD in rover.channels:
            corrected = rover.channel(DIURNAL_CORRECTED_FIELD)
            groups = rover.line_groups()
            line_medians = [float(np.nanmedian(corrected[idx])) for idx in groups.values() if np.any(np.isfinite(corrected[idx]))]
            residual = robust_sigma(line_medians) if line_medians else 0.0
            if residual > float(self.threshold(context, "diurnal_residual_max_nt")):
                findings.append(finding("MAG.DIURNAL.RESIDUAL", QCSeverity.WARNING, f"Robust line-median residual after diurnal correction is {residual:.2f} nT.", suggested_action="Review remaining line bias, timing offset and leveling requirements."))
        return {
            "correction_available": True,
            "maximum_absolute_correction_nt": maximum,
            "median_correction_nt": float(np.nanmedian(correction)) if np.any(finite) else None,
            "correction_robust_sigma_nt": robust_sigma(correction),
            "line_median_residual_nt": residual,
        }, findings, "Diurnal correction magnitude and residual line trend checked.", None
