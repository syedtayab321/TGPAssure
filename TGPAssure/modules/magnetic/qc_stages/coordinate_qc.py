from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, pairwise_distance_m, percentile


class CoordinateQC(MagneticQCStage):
    key = "coordinate"
    display_name = "Coordinate and Navigation"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        mask = dataset.valid_coordinate_mask()
        findings: list[QCFinding] = []
        missing_pct = 100.0 * float(np.count_nonzero(~mask)) / dataset.record_count
        if missing_pct > float(self.threshold(context, "coordinate_missing_max_pct")):
            findings.append(
                finding(
                    "MAG.COORD.MISSING",
                    QCSeverity.ERROR,
                    f"Missing or invalid coordinates affect {missing_pct:.2f}% of records.",
                    suggested_action="Repair GPS records or exclude invalid stations.",
                )
            )
        if np.count_nonzero(mask) < 2:
            return {"missing_coordinate_pct": missing_pct}, findings, "Insufficient valid coordinates for navigation QC.", None

        geographic = bool(dataset.crs and ("4326" in dataset.crs or "wgs84" in dataset.crs.lower()))
        if geographic:
            invalid_geo = mask & (
                (dataset.x < -180.0) | (dataset.x > 180.0)
                | (dataset.y < -90.0) | (dataset.y > 90.0)
            )
            if np.any(invalid_geo):
                findings.append(
                    finding(
                        "MAG.COORD.GEOGRAPHIC_RANGE",
                        QCSeverity.ERROR,
                        f"{np.count_nonzero(invalid_geo)} geographic coordinates are outside valid longitude/latitude ranges.",
                        suggested_action="Verify longitude/latitude mapping and source CRS.",
                    )
                )

        distances_parts = []
        speed_parts = []
        jump_records = np.zeros(dataset.record_count, dtype=bool)
        groups = dataset.line_groups()
        sequences = list(groups.values()) if groups else [np.flatnonzero(mask)]
        jump_limit = float(self.threshold(context, "coordinate_jump_max_m"))
        for indices in sequences:
            valid_indices = indices[mask[indices]]
            if valid_indices.size < 2:
                continue
            line_distances = pairwise_distance_m(dataset.x[valid_indices], dataset.y[valid_indices], geographic=geographic)
            distances_parts.append(line_distances)
            line_time = dataset.timestamps[valid_indices]
            line_dt = np.diff(line_time.astype("datetime64[ms]").astype(np.int64)) / 1000.0
            line_speed = np.divide(line_distances, line_dt, out=np.full_like(line_distances, np.nan), where=line_dt > 0)
            speed_parts.append(line_speed)
            bad = line_distances > jump_limit
            jump_records[valid_indices[1:][bad]] = True
        distances = np.concatenate(distances_parts) if distances_parts else np.empty(0, dtype=float)
        speed = np.concatenate(speed_parts) if speed_parts else np.empty(0, dtype=float)
        jump_mask = distances > jump_limit
        if np.any(jump_mask):
            findings.append(
                finding(
                    "MAG.COORD.JUMP",
                    QCSeverity.ERROR,
                    f"Detected {np.count_nonzero(jump_mask)} coordinate jumps above {jump_limit:.1f} m.",
                    suggested_action="Inspect GPS dropouts, CRS changes or line transitions.",
                    metadata={"maximum_jump_m": float(np.max(distances))},
                )
            )

        classification = str(dataset.metadata.get("acquisition_classification", "moving")).lower()
        speed_limit = float(self.threshold(context, "ground_speed_max_m_s"))
        if classification != "stationary" and dataset.survey_type.value == "ground" and np.any(speed > speed_limit):
            findings.append(
                finding(
                    "MAG.COORD.SPEED",
                    QCSeverity.WARNING,
                    f"{np.count_nonzero(speed > speed_limit)} intervals exceed the ground speed limit of {speed_limit:.1f} m/s.",
                    suggested_action="Check coordinate spikes or vehicle-contaminated acquisition.",
                )
            )

        duplicate_positions = int(np.count_nonzero(distances == 0))
        if duplicate_positions and classification != "stationary":
            findings.append(finding("MAG.COORD.REPEATED", QCSeverity.WARNING, f"Detected {duplicate_positions} consecutive repeated positions."))

        # Use native GPS-quality channels when available. Bulucu logs expose
        # these directly and generic readers may map equivalent columns.
        gps_hdop_p95 = gps_hdop_max = None
        low_satellite_pct = bad_fix_pct = pps_missing_pct = None
        if "gps_hdop" in dataset.channels:
            hdop = dataset.channel("gps_hdop")
            valid_hdop = hdop[np.isfinite(hdop)]
            if valid_hdop.size:
                gps_hdop_p95 = percentile(valid_hdop, 95, 0.0)
                gps_hdop_max = float(np.max(valid_hdop))
                warn_limit = float(self.threshold(context, "gps_hdop_warn_max", 2.5))
                fail_limit = float(self.threshold(context, "gps_hdop_fail_max", 5.0))
                if gps_hdop_p95 > fail_limit:
                    findings.append(
                        finding(
                            "MAG.GPS.HDOP",
                            QCSeverity.ERROR,
                            f"GPS HDOP P95 is {gps_hdop_p95:.2f}, above the failure threshold of {fail_limit:.2f}.",
                            suggested_action="Review poor-positioning intervals and exclude records with unreliable GPS geometry.",
                        )
                    )
                elif gps_hdop_p95 > warn_limit:
                    findings.append(
                        finding(
                            "MAG.GPS.HDOP",
                            QCSeverity.WARNING,
                            f"GPS HDOP P95 is {gps_hdop_p95:.2f}, above the warning threshold of {warn_limit:.2f}.",
                        )
                    )

        if "satellites" in dataset.channels:
            satellites = dataset.channel("satellites")
            valid_sat = satellites[np.isfinite(satellites)]
            if valid_sat.size:
                minimum_satellites = float(self.threshold(context, "gps_satellites_min", 5))
                low_satellite_pct = 100.0 * float(np.count_nonzero(valid_sat < minimum_satellites)) / valid_sat.size
                if low_satellite_pct > 1.0:
                    findings.append(
                        finding(
                            "MAG.GPS.SATELLITES",
                            QCSeverity.WARNING,
                            f"{low_satellite_pct:.2f}% of GPS fixes use fewer than {minimum_satellites:.0f} satellites.",
                            suggested_action="Review GPS coverage and positional stability during low-satellite intervals.",
                        )
                    )

        if "gps_quality" in dataset.channels:
            quality = dataset.channel("gps_quality")
            valid_quality = quality[np.isfinite(quality)]
            if valid_quality.size:
                minimum_quality = float(self.threshold(context, "gps_fix_quality_min", 1.0))
                bad_fix_pct = 100.0 * float(np.count_nonzero(valid_quality < minimum_quality)) / valid_quality.size
                if bad_fix_pct > 0:
                    findings.append(
                        finding(
                            "MAG.GPS.FIX_QUALITY",
                            QCSeverity.ERROR,
                            f"{bad_fix_pct:.3f}% of GPS records are below the minimum fix quality of {minimum_quality:.0f}.",
                            suggested_action="Exclude invalid/no-fix records from spatial processing.",
                        )
                    )

        if "gps_pps_valid" in dataset.channels:
            pps = dataset.channel("gps_pps_valid")
            valid_pps = pps[np.isfinite(pps)]
            if valid_pps.size:
                pps_missing_pct = 100.0 * float(np.count_nonzero(valid_pps < 0.5)) / valid_pps.size
                limit = float(self.threshold(context, "gps_pps_missing_max_pct", 1.0))
                if pps_missing_pct > limit:
                    findings.append(
                        finding(
                            "MAG.GPS.PPS",
                            QCSeverity.WARNING,
                            f"GPS PPS is missing/invalid for {pps_missing_pct:.2f}% of imported samples.",
                            suggested_action="Review logger timing integrity around affected records.",
                        )
                    )

        context.qc_masks["coordinate_jump"] = jump_records
        metrics = {
            "coordinate_crs": dataset.crs,
            "coordinate_units": dataset.coordinate_units,
            "acquisition_classification": classification,
            "missing_coordinate_pct": missing_pct,
            "maximum_coordinate_step_m": float(np.max(distances)) if distances.size else 0.0,
            "median_coordinate_step_m": float(np.median(distances)) if distances.size else 0.0,
            "p95_speed_m_s": percentile(speed, 95, 0.0),
            "maximum_speed_m_s": float(np.nanmax(speed)) if np.any(np.isfinite(speed)) else None,
            "repeated_positions": duplicate_positions,
            "gps_hdop_p95": gps_hdop_p95,
            "gps_hdop_max": gps_hdop_max,
            "low_satellite_pct": low_satellite_pct,
            "bad_fix_quality_pct": bad_fix_pct,
            "gps_pps_missing_pct": pps_missing_pct,
        }
        message = "Coordinate validity, jumps, GPS quality and navigation checked."
        if classification == "stationary":
            message = "Stationary acquisition detected; GPS stability and quality checked without applying rover speed/repeated-position warnings."
        return metrics, findings, message, None
