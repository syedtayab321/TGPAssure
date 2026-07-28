from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import DIURNAL_CORRECTED_FIELD, LEVELED_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class LevelingQC(MagneticQCStage):
    key = "leveling"
    display_name = "Line Leveling"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        if LEVELED_FIELD not in dataset.channels:
            return self.skipped("No leveled magnetic channel is available.")
        values = dataset.channel(LEVELED_FIELD)
        groups = dataset.line_groups()
        if not groups:
            return self.skipped("Line identifiers are required for leveling QC.")
        line_medians = {line: float(np.nanmedian(values[idx])) for line, idx in groups.items() if np.any(np.isfinite(values[idx]))}
        global_median = float(np.median(list(line_medians.values()))) if line_medians else 0.0
        biases = {line: median - global_median for line, median in line_medians.items()}
        maximum_bias = max((abs(value) for value in biases.values()), default=0.0)
        residual = robust_sigma(list(biases.values()))
        findings: list[QCFinding] = []
        if maximum_bias > float(self.threshold(context, "line_bias_max_nt")):
            findings.append(finding("MAG.LEVEL.BIAS", QCSeverity.ERROR, f"Maximum residual line bias is {maximum_bias:.2f} nT.", suggested_action="Review tie constraints, line corrections and regional trend preservation."))
        if residual > float(self.threshold(context, "leveling_residual_max_nt")):
            findings.append(finding("MAG.LEVEL.RESIDUAL", QCSeverity.WARNING, f"Robust residual leveling error is {residual:.2f} nT."))
        correction = None
        if DIURNAL_CORRECTED_FIELD in dataset.channels:
            correction_values = values - dataset.channel(DIURNAL_CORRECTED_FIELD)
            correction = float(np.nanmax(np.abs(correction_values))) if np.any(np.isfinite(correction_values)) else 0.0
            if correction > float(self.threshold(context, "microlevel_correction_max_nt")) * 3.0:
                findings.append(finding("MAG.LEVEL.CORRECTION", QCSeverity.WARNING, f"Maximum leveling correction is {correction:.2f} nT; verify geological signal preservation."))
        return {"line_count": len(line_medians), "maximum_residual_line_bias_nt": maximum_bias, "robust_leveling_residual_nt": residual, "maximum_leveling_correction_nt": correction, "line_biases_nt": biases}, findings, "Residual line bias and leveling correction magnitude checked.", None
