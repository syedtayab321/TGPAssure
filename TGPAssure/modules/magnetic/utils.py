from __future__ import annotations

import json
from typing import Any, Iterable

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus


def finite(values: Iterable[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def median_mad(values: Iterable[float] | np.ndarray) -> tuple[float, float]:
    clean = finite(values)
    if clean.size == 0:
        return float("nan"), float("nan")
    median = float(np.median(clean))
    mad = float(np.median(np.abs(clean - median)))
    return median, mad


def robust_sigma(values: Iterable[float] | np.ndarray) -> float:
    _, mad = median_mad(values)
    return float(1.4826 * mad) if np.isfinite(mad) else float("nan")


def percentile(values: Iterable[float] | np.ndarray, q: float, default: float = float("nan")) -> float:
    clean = finite(values)
    return float(np.percentile(clean, q)) if clean.size else default


def haversine_distance_m(lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    radius = 6_371_008.8
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * radius * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(1.0 - a, 0.0)))


def pairwise_distance_m(x: np.ndarray, y: np.ndarray, geographic: bool = False) -> np.ndarray:
    if x.size < 2:
        return np.empty(0, dtype=float)
    if geographic:
        return haversine_distance_m(x[:-1], y[:-1], x[1:], y[1:])
    return np.hypot(np.diff(x), np.diff(y))


def local_metric_xy(x: np.ndarray, y: np.ndarray, geographic: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Return local metric coordinates for geometric QC.

    Projected coordinates are returned unchanged. Geographic coordinates are
    converted with a local equirectangular approximation centred on the data,
    which is appropriate for survey-scale distance and straightness checks.
    """
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)
    if not geographic or x_values.size == 0:
        return x_values, y_values
    radius = 6_371_008.8
    lon0 = np.radians(float(np.nanmedian(x_values)))
    lat0 = np.radians(float(np.nanmedian(y_values)))
    x_m = radius * (np.radians(x_values) - lon0) * np.cos(lat0)
    y_m = radius * (np.radians(y_values) - lat0)
    return x_m, y_m


def point_in_polygon(x: np.ndarray, y: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    inside = np.zeros(x.size, dtype=bool)
    px = polygon[:, 0]
    py = polygon[:, 1]
    j = len(polygon) - 1
    for i in range(len(polygon)):
        intersects = ((py[i] > y) != (py[j] > y)) & (
            x < (px[j] - px[i]) * (y - py[i]) / ((py[j] - py[i]) + 1e-30) + px[i]
        )
        inside ^= intersects
        j = i
    return inside


def safe_json(data: dict[str, Any]) -> str:
    def default(value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        return str(value)
    return json.dumps(data, default=default, allow_nan=False)


def finding(
    rule_id: str,
    severity: QCSeverity,
    message: str,
    *,
    location_ref: str | None = None,
    suggested_action: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> QCFinding:
    return QCFinding(
        rule_id=rule_id,
        severity=severity,
        message=message,
        location_ref=location_ref,
        suggested_action=suggested_action,
        metadata_json=safe_json(metadata or {}),
    )


def status_from_findings(findings: list[QCFinding]) -> QCStatus:
    severities = {entry.severity for entry in findings}
    if QCSeverity.CRITICAL in severities or QCSeverity.ERROR in severities:
        return QCStatus.FAIL
    if QCSeverity.WARNING in severities:
        return QCStatus.WARN
    return QCStatus.PASS


def score_from_outcomes(statuses: Iterable[QCStatus]) -> float:
    weights = {QCStatus.PASS: 1.0, QCStatus.WARN: 0.65, QCStatus.SKIPPED: 0.8, QCStatus.FAIL: 0.0}
    values = [weights.get(status, 0.5) for status in statuses]
    return round(100.0 * float(np.mean(values)), 2) if values else 0.0
