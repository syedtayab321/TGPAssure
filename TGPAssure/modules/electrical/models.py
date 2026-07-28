from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from modules.electrical.constants import ElectricalMethod, METHOD_LABELS


@dataclass
class ElectricalDataset:
    source_path: Path
    method: ElectricalMethod
    columns: dict[str, np.ndarray]
    raw_headers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_format: str = "delimited"

    @property
    def record_count(self) -> int:
        if not self.columns:
            return 0
        return max((len(v) for v in self.columns.values()), default=0)

    @property
    def method_label(self) -> str:
        return METHOD_LABELS.get(self.method, self.method.value)

    def has(self, name: str) -> bool:
        return name in self.columns and len(self.columns[name]) == self.record_count

    def values(self, name: str, default: float = np.nan) -> np.ndarray:
        if self.has(name):
            return self.columns[name]
        return np.full(self.record_count, default, dtype=float)

    def numeric(self, name: str) -> np.ndarray:
        values = self.values(name)
        if np.issubdtype(values.dtype, np.number):
            return values.astype(float, copy=False)
        output = np.full(len(values), np.nan, dtype=float)
        for i, value in enumerate(values):
            try:
                output[i] = float(value)
            except (TypeError, ValueError):
                pass
        return output

    def text(self, name: str) -> np.ndarray:
        values = self.values(name, default=np.nan)
        return np.asarray(["" if _is_missing(v) else str(v) for v in values], dtype=object)

    def set_column(self, name: str, values: Iterable[Any]) -> None:
        array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values)
        if self.columns and len(array) != self.record_count:
            raise ValueError(f"Column {name!r} has {len(array)} values; expected {self.record_count}")
        self.columns[name] = array

    def copy(self) -> "ElectricalDataset":
        return ElectricalDataset(
            source_path=self.source_path,
            method=self.method,
            columns={key: value.copy() for key, value in self.columns.items()},
            raw_headers=list(self.raw_headers),
            metadata=dict(self.metadata),
            source_format=self.source_format,
        )

    def summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "source_path": str(self.source_path),
            "source_file": self.source_path.name,
            "method": self.method.value,
            "method_label": self.method_label,
            "record_count": self.record_count,
            "source_format": self.source_format,
            "columns": sorted(self.columns),
        }
        for field in (
            "apparent_resistivity_ohm_m", "chargeability_mv_v", "sp_mv", "frequency_hz",
            "phase_mrad", "current_ma", "voltage_mv", "electric_field_mv_km", "electric_field_x_mv_km",
            "electric_field_y_mv_km", "contact_resistance_ohm", "stack_std_pct",
        ):
            if not self.has(field):
                continue
            arr = self.numeric(field)
            valid = arr[np.isfinite(arr)]
            if valid.size:
                summary[f"{field}_min"] = float(np.min(valid))
                summary[f"{field}_median"] = float(np.median(valid))
                summary[f"{field}_max"] = float(np.max(valid))
        if self.has("line_id"):
            summary["line_count"] = len({v for v in self.text("line_id") if v})
        summary.update(self.metadata)
        return summary


@dataclass
class QcFinding:
    code: str
    severity: str
    stage_key: str
    title: str
    message: str
    suggested_action: str = ""
    row_index: int | None = None
    observed_value: float | str | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    unit: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_history_dict(self) -> dict[str, Any]:
        return {
            "finding_code": self.code,
            "severity": self.severity,
            "stage_key": self.stage_key,
            "category": "electrical",
            "title": self.title,
            "description": self.message,
            "suggested_action": self.suggested_action,
            "trace_index": self.row_index,
            "observed_value": self.observed_value,
            "expected_min": self.expected_min,
            "expected_max": self.expected_max,
            "unit": self.unit,
            "context": self.context,
        }


@dataclass
class QcStageResult:
    stage_key: str
    stage_name: str
    status: str
    score: float
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)
    findings: list[QcFinding] = field(default_factory=list)
    duration_ms: int = 0

    def to_history_dict(self, order: int) -> dict[str, Any]:
        return {
            "stage_key": self.stage_key,
            "stage_name": self.stage_name,
            "stage_order": order,
            "status": "completed",
            "result": self.status,
            "score": self.score,
            "metrics": self.metrics,
            "message": self.message,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ElectricalQcResult:
    dataset: ElectricalDataset
    stages: list[QcStageResult]
    score: float
    status: str
    profile_name: str
    thresholds: dict[str, float]
    duration_ms: int

    @property
    def findings(self) -> list[QcFinding]:
        return [finding for stage in self.stages for finding in stage.findings]

    def summary(self) -> dict[str, Any]:
        severity_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for finding in self.findings:
            severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        for stage in self.stages:
            status_counts[stage.status] = status_counts.get(stage.status, 0) + 1
        return {
            **self.dataset.summary(),
            "overall_score": round(self.score, 2),
            "overall_status": self.status,
            "profile": self.profile_name,
            "duration_ms": self.duration_ms,
            "stage_count": len(self.stages),
            "finding_count": len(self.findings),
            "severity_counts": severity_counts,
            "stage_status_counts": status_counts,
            "thresholds": self.thresholds,
        }


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(np.isnan(value))
    except (TypeError, ValueError):
        return str(value).strip() == ""
