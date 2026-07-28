from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, pairwise_distance_m, percentile


class StationSpacingQC(MagneticQCStage):
    key = "station_spacing"
    display_name = "Station Spacing"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        groups = context.rover_dataset.line_groups()
        if not groups:
            return self.skipped("Line identifiers are unavailable; station spacing cannot be evaluated.")
        dataset = context.rover_dataset
        nominal = float(self.threshold(context, "nominal_station_spacing_m"))
        tolerance = float(self.threshold(context, "station_spacing_tolerance_pct")) / 100.0
        lower, upper = nominal * (1.0 - tolerance), nominal * (1.0 + tolerance)
        all_spacing: list[float] = []
        findings: list[QCFinding] = []
        line_metrics: dict[str, dict[str, Any]] = {}
        geographic = bool(dataset.crs and "4326" in dataset.crs)
        for line, indices in groups.items():
            valid = np.isfinite(dataset.x[indices]) & np.isfinite(dataset.y[indices])
            spacing = pairwise_distance_m(dataset.x[indices][valid], dataset.y[indices][valid], geographic)
            spacing = spacing[np.isfinite(spacing)]
            if not spacing.size:
                continue
            all_spacing.extend(spacing.tolist())
            outliers = (spacing < lower) | (spacing > upper)
            outlier_pct = 100.0 * np.count_nonzero(outliers) / spacing.size
            line_metrics[line] = {"median_spacing_m": float(np.median(spacing)), "maximum_spacing_m": float(np.max(spacing)), "outlier_pct": float(outlier_pct)}
            if outlier_pct > 10.0:
                findings.append(finding("MAG.SPACING.LINE", QCSeverity.WARNING, f"{outlier_pct:.1f}% of station intervals on line {line} fall outside {lower:.1f}–{upper:.1f} m.", location_ref=f"line:{line}"))
        spacing_array = np.asarray(all_spacing, dtype=float)
        if not spacing_array.size:
            return self.skipped("No valid within-line station intervals were found.")
        overall_outlier_pct = 100.0 * np.count_nonzero((spacing_array < lower) | (spacing_array > upper)) / spacing_array.size
        if overall_outlier_pct > 10.0:
            findings.append(finding("MAG.SPACING.OVERALL", QCSeverity.WARNING, f"Overall station-spacing non-compliance is {overall_outlier_pct:.1f}%.", suggested_action="Review missed stations, line speed and nominal spacing configuration."))
        for line, metrics in line_metrics.items():
            context.line_statistics.setdefault(line, {}).update(metrics)
        return {
            "nominal_spacing_m": nominal,
            "median_spacing_m": float(np.median(spacing_array)),
            "p95_spacing_m": percentile(spacing_array, 95, 0.0),
            "maximum_spacing_m": float(np.max(spacing_array)),
            "spacing_outlier_pct": float(overall_outlier_pct),
            "line_spacing_metrics": line_metrics,
        }, findings, "Within-line station spacing and missed-station indicators checked.", None
