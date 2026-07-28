from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, local_metric_xy


class LineGeometryQC(MagneticQCStage):
    key = "line_geometry"
    display_name = "Line Geometry"

    @staticmethod
    def _orientation_and_deviation(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
        if x.size < 2:
            return float("nan"), float("nan"), 0.0
        dx = x[-1] - x[0]
        dy = y[-1] - y[0]
        length = float(np.sum(np.hypot(np.diff(x), np.diff(y))))
        azimuth = float((np.degrees(np.arctan2(dx, dy)) + 360.0) % 180.0)
        norm = np.hypot(dx, dy)
        if norm == 0:
            return azimuth, float("inf"), length
        deviation = np.abs(dy * (x - x[0]) - dx * (y - y[0])) / norm
        return azimuth, float(np.nanmax(deviation)), length

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        groups = context.rover_dataset.line_groups()
        if not groups:
            return self.skipped("Line identifiers are unavailable; line geometry cannot be evaluated.")
        dataset = context.rover_dataset
        findings: list[QCFinding] = []
        line_stats: dict[str, dict[str, Any]] = {}
        max_deviation = float(self.threshold(context, "line_deviation_max_m"))
        azimuth_tolerance = float(self.threshold(context, "line_azimuth_tolerance_deg"))
        expected_traverse = self.threshold(context, "expected_traverse_azimuth_deg")
        expected_tie = self.threshold(context, "expected_tie_azimuth_deg")
        for line, indices in groups.items():
            valid = np.isfinite(dataset.x[indices]) & np.isfinite(dataset.y[indices])
            line_indices = indices[valid]
            if line_indices.size < 2:
                findings.append(finding("MAG.LINE.INSUFFICIENT", QCSeverity.WARNING, f"Line {line} has fewer than two valid coordinate records.", location_ref=f"line:{line}"))
                continue
            x, y = dataset.x[line_indices], dataset.y[line_indices]
            geographic = bool(dataset.crs and ("4326" in dataset.crs or "wgs84" in dataset.crs.lower()))
            metric_x, metric_y = local_metric_xy(x, y, geographic)
            azimuth, deviation, length = self._orientation_and_deviation(metric_x, metric_y)
            type_values = dataset.line_type[line_indices].astype(str)
            line_type = max(set(type_values), key=list(type_values).count) if type_values.size else "unknown"
            line_stats[line] = {"line_type": line_type, "record_count": int(line_indices.size), "length_m": length, "azimuth_deg": azimuth, "max_deviation_m": deviation}
            if deviation > max_deviation:
                findings.append(finding("MAG.LINE.STRAIGHTNESS", QCSeverity.WARNING, f"Line {line} deviates up to {deviation:.1f} m from its end-to-end axis.", location_ref=f"line:{line}", suggested_action="Review navigation, terrain constraints and line assignment."))
            expected = expected_tie if line_type == "tie" else expected_traverse
            if expected is not None:
                difference = abs(((azimuth - float(expected) + 90.0) % 180.0) - 90.0)
                if difference > azimuth_tolerance:
                    findings.append(finding("MAG.LINE.AZIMUTH", QCSeverity.WARNING, f"Line {line} azimuth differs by {difference:.1f}° from the expected orientation.", location_ref=f"line:{line}"))
        context.line_statistics.update(line_stats)
        deviations = [entry["max_deviation_m"] for entry in line_stats.values()]
        lengths = [entry["length_m"] for entry in line_stats.values()]
        return {
            "line_count": len(line_stats),
            "maximum_line_deviation_m": max(deviations, default=0.0),
            "total_line_length_m": sum(lengths),
            "line_statistics": line_stats,
        }, findings, "Line orientation, length and straightness checked.", None
