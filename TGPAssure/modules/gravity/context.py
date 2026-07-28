from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from modules.gravity.models import GravityDataset, GravityStageOutcome


@dataclass
class GravityQcContext:
    observations: GravityDataset
    base: GravityDataset | None = None
    profile_name: str = "standard"
    thresholds: dict[str, float] = field(default_factory=dict)
    density_g_cm3: float = 2.67
    processing_products: dict[str, Any] = field(default_factory=dict)
    stage_outcomes: dict[str, GravityStageOutcome] = field(default_factory=dict)
    repeat_statistics: list[dict[str, Any]] = field(default_factory=list)
    loop_closures: list[dict[str, Any]] = field(default_factory=list)
    crossovers: list[dict[str, Any]] = field(default_factory=list)
    progress_callback: Callable[[int, int, str], None] | None = None
    cancellation_check: Callable[[], bool] | None = None

    def report_progress(self, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(current, total, message)

    def cancelled(self) -> bool:
        return bool(self.cancellation_check and self.cancellation_check())
