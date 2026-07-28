from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import DIURNAL_CORRECTED_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, local_metric_xy, median_mad


class CulturalNoiseQC(MagneticQCStage):
    key = "cultural_noise"
    display_name = "Cultural Noise"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        _, values = dataset.first_available_channel((DIURNAL_CORRECTED_FIELD, RAW_TOTAL_FIELD))
        if values.size < 5:
            return self.skipped("Insufficient records for cultural-noise screening.")

        # For stationary acquisitions, spatial-repeat logic is not meaningful:
        # GPS jitter makes many samples occupy the same location. Screen only
        # temporal high-gradient candidates and leave source attribution to the
        # reviewer.
        classification = str(dataset.metadata.get("acquisition_classification", "moving")).lower()
        gradient = np.abs(np.gradient(values))
        median, mad = median_mad(gradient)
        if not np.isfinite(mad) or mad <= 0:
            limit = float("inf")
        else:
            limit = median + float(self.threshold(context, "cultural_noise_outlier_factor")) * 1.4826 * mad
        mask = np.isfinite(gradient) & (gradient > limit)
        context.qc_masks["cultural_noise_candidates"] = mask
        candidate_pct = 100.0 * np.count_nonzero(mask) / values.size
        findings: list[QCFinding] = []

        if classification == "stationary":
            if candidate_pct > 2.0:
                findings.append(
                    finding(
                        "MAG.CULTURAL.TEMPORAL_CANDIDATES",
                        QCSeverity.WARNING,
                        f"Rapid magnetic changes affect {candidate_pct:.2f}% of the stationary record.",
                        suggested_action="Review nearby vehicles, metal movement, electrical equipment and operator activity; do not automatically classify these changes as geology.",
                    )
                )
            return {
                "acquisition_classification": classification,
                "candidate_count": int(np.count_nonzero(mask)),
                "candidate_pct": candidate_pct,
                "repeated_location_count": 0,
                "effective_gradient_limit_nt_per_sample": None if not np.isfinite(limit) else float(limit),
            }, findings, "Stationary acquisition screened for rapid temporal disturbances; spatial cultural-repeat logic was not applied.", None

        coordinate_bins: dict[tuple[int, int], list[int]] = {}
        spacing = max(float(self.threshold(context, "nominal_station_spacing_m")), 1.0)
        geographic = bool(dataset.crs and ("4326" in dataset.crs or "wgs84" in dataset.crs.lower()))
        valid_coordinates = dataset.valid_coordinate_mask()
        metric_x, metric_y = local_metric_xy(dataset.x, dataset.y, geographic)
        for index in np.flatnonzero(valid_coordinates & mask):
            key = (int(round(metric_x[index] / spacing)), int(round(metric_y[index] / spacing)))
            coordinate_bins.setdefault(key, []).append(index)
        repeated_bins = {key: indices for key, indices in coordinate_bins.items() if len(indices) > 1}

        if repeated_bins:
            findings.append(
                finding(
                    "MAG.CULTURAL.REPEATED",
                    QCSeverity.WARNING,
                    f"Detected {len(repeated_bins)} spatially repeatable high-gradient anomaly locations that may be cultural.",
                    suggested_action="Compare with roads, fences, power lines, pipelines, vehicles and site notes.",
                )
            )
        elif candidate_pct > 2.0:
            findings.append(
                finding(
                    "MAG.CULTURAL.CANDIDATES",
                    QCSeverity.WARNING,
                    f"High-gradient anomaly candidates affect {candidate_pct:.2f}% of records.",
                    suggested_action="Review field notes and infrastructure layers before masking any anomaly.",
                )
            )
        return {
            "acquisition_classification": classification,
            "candidate_count": int(np.count_nonzero(mask)),
            "candidate_pct": candidate_pct,
            "repeated_location_count": len(repeated_bins),
            "effective_gradient_limit_nt_per_sample": None if not np.isfinite(limit) else float(limit),
        }, findings, "Potential cultural contamination screened using robust gradients and metric spatial repeatability.", None
