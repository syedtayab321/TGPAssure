from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from modules.magnetic.models import MagneticBoundary, MagneticDataset, MagneticStageOutcome


@dataclass
class MagneticQcContext:
    rover_dataset: MagneticDataset
    base_dataset: MagneticDataset | None = None
    survey_boundary: MagneticBoundary | None = None
    profile_name: str = "standard"
    thresholds: dict[str, Any] = field(default_factory=dict)
    stage_outcomes: dict[str, MagneticStageOutcome] = field(default_factory=dict)
    line_statistics: dict[str, dict[str, Any]] = field(default_factory=dict)
    base_statistics: dict[str, Any] = field(default_factory=dict)
    processing_products: dict[str, Any] = field(default_factory=dict)
    qc_masks: dict[str, np.ndarray] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    progress_callback: Callable[[int, int, str], None] | None = None
    cancellation_check: Callable[[], bool] | None = None

    def cancelled(self) -> bool:
        return bool(self.cancellation_check and self.cancellation_check())

    def report_progress(self, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(current, total, message)
