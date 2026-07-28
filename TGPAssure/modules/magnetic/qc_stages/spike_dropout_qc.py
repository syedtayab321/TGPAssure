from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, median_mad


class SpikeDropoutQC(MagneticQCStage):
    key = "spike_dropout"
    display_name = "Spikes and Dropouts"

    @staticmethod
    def _rolling_median(values: np.ndarray, window: int = 7) -> np.ndarray:
        window = max(3, int(window) | 1)
        half = window // 2
        padded = np.pad(values, (half, half), mode="edge")
        return np.array([np.nanmedian(padded[index:index + window]) for index in range(values.size)], dtype=float)

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        values = dataset.channel(RAW_TOTAL_FIELD)
        finite = np.isfinite(values)
        working = values.copy()
        if np.any(finite):
            working[~finite] = np.nanmedian(values[finite])
        local = self._rolling_median(working)
        residual = values - local
        median, mad = median_mad(residual)
        factor = float(self.threshold(context, "spike_outlier_factor"))
        robust_limit = factor * 1.4826 * mad if np.isfinite(mad) and mad > 0 else float(self.threshold(context, "spike_threshold_nt"))
        absolute_limit = float(self.threshold(context, "spike_threshold_nt"))
        limit = max(absolute_limit, robust_limit)
        spike_mask = finite & (np.abs(residual - median) > limit)
        dropout_mask = ~finite | (values == 0.0)
        dropout_pct = 100.0 * np.count_nonzero(dropout_mask) / values.size
        frozen_mask = np.zeros(values.size, dtype=bool)
        maximum_run = 1
        run_start = 0
        for index in range(1, values.size):
            if np.isfinite(values[index]) and values[index] == values[index - 1]:
                run = index - run_start + 1
                maximum_run = max(maximum_run, run)
            else:
                if index - run_start > int(self.threshold(context, "frozen_sequence_max_samples")):
                    frozen_mask[run_start:index] = True
                run_start = index
        if values.size - run_start > int(self.threshold(context, "frozen_sequence_max_samples")):
            frozen_mask[run_start:] = True
        findings: list[QCFinding] = []
        if np.any(spike_mask):
            severity = QCSeverity.ERROR if np.count_nonzero(spike_mask) / values.size > 0.01 else QCSeverity.WARNING
            findings.append(finding("MAG.SPIKE.DETECTED", severity, f"Detected {np.count_nonzero(spike_mask)} robust total-field spikes above {limit:.2f} nT.", suggested_action="Review the flagged records and apply traceable despiking only after geological verification."))
        if dropout_pct > float(self.threshold(context, "dropout_max_pct")):
            findings.append(finding("MAG.DROPOUT.EXCESS", QCSeverity.ERROR, f"Dropouts affect {dropout_pct:.2f}% of total-field records."))
        if np.any(frozen_mask):
            findings.append(finding("MAG.FROZEN.SEQUENCE", QCSeverity.ERROR, f"Frozen sensor sequences affect {np.count_nonzero(frozen_mask)} records."))
        context.qc_masks["spikes"] = spike_mask
        context.qc_masks["dropouts"] = dropout_mask
        context.qc_masks["frozen"] = frozen_mask
        return {
            "spike_count": int(np.count_nonzero(spike_mask)),
            "spike_pct": 100.0 * np.count_nonzero(spike_mask) / values.size,
            "dropout_count": int(np.count_nonzero(dropout_mask)),
            "dropout_pct": dropout_pct,
            "frozen_record_count": int(np.count_nonzero(frozen_mask)),
            "maximum_frozen_run_samples": maximum_run,
            "effective_spike_limit_nt": limit,
        }, findings, "Robust local spikes, missing values and frozen sensor sequences checked.", None
