from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.models import MagneticStageOutcome
from modules.magnetic.utils import finding, status_from_findings


class MagneticQCStage(ABC):
    key = "base"
    display_name = "Magnetic QC Stage"

    def run(self, context: MagneticQcContext) -> MagneticStageOutcome:
        started = time.perf_counter()
        try:
            metrics, findings, message, status = self.evaluate(context)
            clean_metrics = self._clean(metrics)
            resolved_status = status or status_from_findings(findings)
            return MagneticStageOutcome(
                stage_key=self.key,
                display_name=self.display_name,
                status=resolved_status,
                metrics=clean_metrics,
                findings=findings,
                message=message,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            critical = finding(
                f"{self.key}.execution_error",
                QCSeverity.CRITICAL,
                f"{self.display_name} could not be completed: {exc}",
                suggested_action="Review the input format, stage prerequisites and application log.",
                metadata={"exception_type": type(exc).__name__},
            )
            return MagneticStageOutcome(
                stage_key=self.key,
                display_name=self.display_name,
                status=QCStatus.FAIL,
                metrics={"error": str(exc)},
                findings=[critical],
                message=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    @abstractmethod
    def evaluate(
        self, context: MagneticQcContext
    ) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        raise NotImplementedError

    @staticmethod
    def threshold(context: MagneticQcContext, key: str, default: Any = None) -> Any:
        return context.thresholds.get(key, default)

    @classmethod
    def skipped(cls, reason: str, metrics: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus]:
        return metrics or {}, [], reason, QCStatus.SKIPPED

    @classmethod
    def _clean(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._clean(item) for item in value]
        if isinstance(value, np.ndarray):
            return [cls._clean(item) for item in value.tolist()]
        if isinstance(value, np.generic):
            return cls._clean(value.item())
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return value
