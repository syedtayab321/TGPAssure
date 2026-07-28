from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import DIURNAL_CORRECTED_FIELD, LEVELED_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, local_metric_xy


class TieLineQC(MagneticQCStage):
    key = "tie_line"
    display_name = "Tie-Line Misclosure"

    @staticmethod
    def _nearest_intersections(dataset, values, traverse_idx: np.ndarray, tie_idx: np.ndarray, tolerance_m: float) -> list[dict[str, float]]:
        valid_traverse = (
            np.isfinite(dataset.x[traverse_idx])
            & np.isfinite(dataset.y[traverse_idx])
            & np.isfinite(values[traverse_idx])
        )
        valid_tie = (
            np.isfinite(dataset.x[tie_idx])
            & np.isfinite(dataset.y[tie_idx])
            & np.isfinite(values[tie_idx])
        )
        traverse_records = traverse_idx[valid_traverse]
        tie_records = tie_idx[valid_tie]
        if traverse_records.size == 0 or tie_records.size == 0:
            return []
        geographic = bool(dataset.crs and ("4326" in dataset.crs or "wgs84" in dataset.crs.lower()))
        all_x = np.r_[dataset.x[traverse_records], dataset.x[tie_records]]
        all_y = np.r_[dataset.y[traverse_records], dataset.y[tie_records]]
        metric_x, metric_y = local_metric_xy(all_x, all_y, geographic)
        traverse_points = np.column_stack((metric_x[: traverse_records.size], metric_y[: traverse_records.size]))
        tie_points = np.column_stack((metric_x[traverse_records.size :], metric_y[traverse_records.size :]))
        try:
            from scipy.spatial import cKDTree

            tree = cKDTree(tie_points)
            distances, nearest = tree.query(traverse_points, k=1, distance_upper_bound=tolerance_m)
            valid = np.isfinite(distances) & (nearest < tie_records.size)
            if not np.any(valid):
                return []
            candidate_rows = np.flatnonzero(valid)
            # Keep the closest traverse sample for each matched tie sample so a
            # dense intersection does not contribute dozens of duplicate picks.
            best_by_tie: dict[int, tuple[float, int]] = {}
            for row in candidate_rows:
                tie_position = int(nearest[row])
                distance = float(distances[row])
                current = best_by_tie.get(tie_position)
                if current is None or distance < current[0]:
                    best_by_tie[tie_position] = (distance, int(row))
            results = []
            for tie_position, (distance, row) in best_by_tie.items():
                traverse_record = int(traverse_records[row])
                tie_record = int(tie_records[tie_position])
                results.append(
                    {
                        "distance_m": distance,
                        "misclosure_nt": float(values[traverse_record] - values[tie_record]),
                        "traverse_record": traverse_record,
                        "tie_record": tie_record,
                    }
                )
            return results
        except ImportError:
            results: list[dict[str, float]] = []
            for row, point in enumerate(traverse_points):
                distance = np.hypot(tie_points[:, 0] - point[0], tie_points[:, 1] - point[1])
                nearest = int(np.argmin(distance))
                if distance[nearest] <= tolerance_m:
                    results.append(
                        {
                            "distance_m": float(distance[nearest]),
                            "misclosure_nt": float(values[traverse_records[row]] - values[tie_records[nearest]]),
                            "traverse_record": int(traverse_records[row]),
                            "tie_record": int(tie_records[nearest]),
                        }
                    )
            return results

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        groups = dataset.line_groups()
        traverse_groups = {line: idx for line, idx in groups.items() if np.any(dataset.line_type[idx].astype(str) == "traverse")}
        tie_groups = {line: idx for line, idx in groups.items() if np.any(dataset.line_type[idx].astype(str) == "tie")}
        if not traverse_groups or not tie_groups:
            return self.skipped("Both traverse and tie-line identifiers are required for misclosure QC.")
        channel_name, values = dataset.first_available_channel((LEVELED_FIELD, DIURNAL_CORRECTED_FIELD, RAW_TOTAL_FIELD))
        tolerance = max(5.0, float(self.threshold(context, "nominal_station_spacing_m")))
        intersections: list[dict[str, Any]] = []
        for traverse, traverse_idx in traverse_groups.items():
            for tie, tie_idx in tie_groups.items():
                candidates = self._nearest_intersections(dataset, values, traverse_idx, tie_idx, tolerance)
                if candidates:
                    best = min(candidates, key=lambda item: item["distance_m"])
                    best.update({"traverse": traverse, "tie": tie})
                    intersections.append(best)
        if not intersections:
            return self.skipped("No traverse/tie intersections were found within the station-spacing tolerance.")
        misclosures = np.asarray([entry["misclosure_nt"] for entry in intersections], dtype=float)
        maximum = float(np.max(np.abs(misclosures)))
        rms = float(np.sqrt(np.mean(misclosures ** 2)))
        findings: list[QCFinding] = []
        if maximum > float(self.threshold(context, "tie_misclosure_max_nt")):
            findings.append(finding("MAG.TIE.MAX", QCSeverity.ERROR, f"Maximum absolute tie misclosure is {maximum:.2f} nT.", suggested_action="Review line corrections and execute controlled tie-line leveling."))
        if rms > float(self.threshold(context, "tie_misclosure_rms_max_nt")):
            findings.append(finding("MAG.TIE.RMS", QCSeverity.WARNING, f"Tie misclosure RMS is {rms:.2f} nT."))
        context.processing_products["tie_intersections"] = intersections
        return {"source_channel": channel_name, "intersection_count": len(intersections), "mean_misclosure_nt": float(np.mean(misclosures)), "rms_misclosure_nt": rms, "maximum_absolute_misclosure_nt": maximum, "intersections": intersections[:500]}, findings, "Traverse/tie intersection misclosures checked.", None
