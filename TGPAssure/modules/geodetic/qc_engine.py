from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from modules.geodetic.models import (
    GeodeticDataset,
    GeodeticFinding,
    GeodeticMetric,
    GeodeticQcResult,
)


@dataclass(frozen=True)
class QcProfile:
    name: str
    label: str
    description: str
    thresholds: dict[str, float]


QC_PROFILES: dict[str, QcProfile] = {
    "project_default": QcProfile(
        "project_default",
        "Project / Legacy DC Screening",
        "Conservative editable screening defaults inspired by common field-controller QC displays; project specifications take precedence.",
        {
            "min_satellites": 5.0,
            "relative_dops": 2.5,
            "pdop": 5.0,
            "hdop": 1.5,
            "vdop": 3.0,
            "rms_m": 0.05,
            "horizontal_sd_m": 0.03,
            "vertical_sd_m": 0.05,
            "horizontal_precision_m": 0.05,
            "vertical_precision_m": 0.10,
        },
    ),
    "ngs_rt_screen": QcProfile(
        "ngs_rt_screen",
        "NGS-style RT GNSS Screening",
        "Screening profile based on example NGS real-time GNSS guidance; it is not a universal acceptance specification.",
        {
            "min_satellites": 7.0,
            "relative_dops": 3.0,
            "pdop": 2.5,
            "hdop": 2.0,
            "vdop": 3.0,
            "rms_m": 0.04,
            "horizontal_sd_m": 0.02,
            "vertical_sd_m": 0.04,
            "horizontal_precision_m": 0.02,
            "vertical_precision_m": 0.04,
        },
    ),
}

METRIC_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    ("min_satellites", "Minimum Number of Satellites", "satellites", "min"),
    ("relative_dops", "Relative DOPs", "", "max"),
    ("pdop", "PDOP", "", "max"),
    ("hdop", "HDOP", "", "max"),
    ("vdop", "VDOP", "", "max"),
    ("rms_m", "RMS", "m", "max"),
    ("positions_used", "Number of Positions Used", "positions", "min"),
    ("horizontal_sd_m", "Horizontal SD", "m", "max"),
    ("vertical_sd_m", "Vertical SD", "m", "max"),
    ("delta_time_s", "Delta Time", "s", "max"),
)


class GeodeticQcEngine:
    """Auditable GNSS/DC QC using configurable thresholds and explicit evidence.

    Thresholds are intentionally profiles/settings, not hard-coded claims of
    universal compliance. Every failure records the observed value and criterion.
    """

    def __init__(self, profile: str = "project_default", overrides: dict[str, float] | None = None) -> None:
        if profile not in QC_PROFILES:
            raise ValueError(f"Unknown geodetic QC profile: {profile}")
        self.profile = QC_PROFILES[profile]
        self.thresholds = dict(self.profile.thresholds)
        if overrides:
            self.thresholds.update({str(k): float(v) for k, v in overrides.items()})

    def run(self, dataset: GeodeticDataset) -> GeodeticQcResult:
        findings: list[GeodeticFinding] = []
        metrics = self._metrics(dataset)
        checks: dict[str, Any] = {}

        self._check_document_structure(dataset, findings, checks)
        self._check_metrics(metrics, findings, checks)
        self._check_dop_consistency(dataset, findings, checks)
        self._check_positions(dataset, findings, checks)
        self._check_vectors(dataset, findings, checks)
        self._check_gps_time(dataset, findings, checks)
        self._check_survey_settings(dataset, findings, checks)

        failures = sum(1 for f in findings if f.severity == "FAIL")
        warnings = sum(1 for f in findings if f.severity == "WARN")
        info = sum(1 for f in findings if f.severity == "INFO")
        score = max(0.0, min(100.0, 100.0 - failures * 10.0 - warnings * 2.5))
        status = "FAIL" if failures else ("WARN" if warnings else "PASS")
        checks.update({"failures": failures, "warnings": warnings, "information": info})
        return GeodeticQcResult(self.profile.name, status, score, metrics, findings, checks)

    def _metrics(self, dataset: GeodeticDataset) -> dict[str, GeodeticMetric]:
        output: dict[str, GeodeticMetric] = {}
        for key, label, unit, direction in METRIC_DEFINITIONS:
            values = dataset.numeric_series("C6", key)
            threshold = self.thresholds.get(key)
            # positions_used is meaningful with a lower bound of 1 even without a profile setting.
            if key == "positions_used" and threshold is None:
                threshold = 1.0
            output[key] = GeodeticMetric(key, label, unit, values, threshold, direction)
        return output

    def _check_document_structure(self, dataset: GeodeticDataset, findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        available = dataset.available_record_ids()
        checks["record_ids"] = sorted(available)
        expected_groups = {
            "header/job": {"00", "10"},
            "coordinate system": {"C8"},
            "equipment": {"E2"},
            "survey masks/antenna": {"56", "57"},
        }
        for label, ids in expected_groups.items():
            if not available.intersection(ids):
                findings.append(GeodeticFinding(
                    f"MISSING_{label.upper().replace('/', '_').replace(' ', '_')}", "WARN",
                    f"{label.title()} record not found",
                    f"No recognized {label} record was parsed. This reduces auditability but does not by itself invalidate position observations.",
                    suggested_action="Confirm the controller/export format and include project, coordinate-system and equipment metadata in the deliverable.",
                ))
        if not available.intersection({"66", "68", "67"}):
            findings.append(GeodeticFinding(
                "NO_POSITION_VECTOR_RECORDS", "FAIL", "No geodetic observations found",
                "No GPS position, local position or GPS vector records were recognized.",
                suggested_action="Check the source export and parser mapping before using the dataset for survey control.",
            ))
        if "C6" not in available:
            findings.append(GeodeticFinding(
                "NO_C6_QC_RECORDS", "WARN", "No C6 QC records found",
                "DOP, satellite-count, RMS and standard-deviation time-series QC cannot be evaluated from this file.",
                suggested_action="Export controller QC records or load a companion QC table when available.",
            ))

    def _check_metrics(self, metrics: dict[str, GeodeticMetric], findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        metric_summary: dict[str, Any] = {}
        for key, metric in metrics.items():
            finite = metric.finite
            if not finite.size:
                metric_summary[key] = {"count": 0}
                continue
            summary = {
                "count": int(finite.size), "min": float(np.min(finite)), "median": float(np.median(finite)), "max": float(np.max(finite)),
                "threshold": metric.threshold, "direction": metric.direction,
            }
            if metric.threshold is not None:
                if metric.direction == "min":
                    bad = finite < metric.threshold
                    extreme = float(np.min(finite))
                    comparator = ">="
                else:
                    bad = finite > metric.threshold
                    extreme = float(np.max(finite))
                    comparator = "<="
                count = int(np.count_nonzero(bad))
                summary["violations"] = count
                if count:
                    severity = "FAIL" if count / finite.size > 0.10 else "WARN"
                    findings.append(GeodeticFinding(
                        f"QC_{key.upper()}_LIMIT", severity, f"{metric.label} exceeds screening criterion",
                        f"{count} of {finite.size} finite observations violate {metric.label} {comparator} {metric.threshold:g}{(' ' + metric.unit) if metric.unit else ''}.",
                        record_id="C6", observed=extreme, limit=metric.threshold,
                        suggested_action="Review satellite geometry/obstructions, occupation duration, corrections, antenna setup and project-specific acceptance criteria.",
                    ))
            metric_summary[key] = summary
        checks["metrics"] = metric_summary

    def _check_dop_consistency(self, dataset: GeodeticDataset, findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        residuals: list[float] = []
        evaluated = 0
        for record in dataset.records_for("C6"):
            try:
                pdop = float(record.values["pdop"]); hdop = float(record.values["hdop"]); vdop = float(record.values["vdop"])
            except (KeyError, TypeError, ValueError):
                continue
            if min(pdop, hdop, vdop) < 0:
                findings.append(GeodeticFinding(
                    "NEGATIVE_DOP", "FAIL", "Negative DOP value",
                    f"PDOP/HDOP/VDOP must be non-negative; observed {pdop:g}/{hdop:g}/{vdop:g}.",
                    "C6", record.line_number, suggested_action="Verify field mapping and source-controller export."
                ))
                continue
            expected = float(np.hypot(hdop, vdop))
            residual = abs(pdop - expected)
            residuals.append(residual); evaluated += 1
            tolerance = max(0.20, expected * 0.15)
            if residual > tolerance:
                findings.append(GeodeticFinding(
                    "DOP_COMPONENT_INCONSISTENCY", "WARN", "DOP components are internally inconsistent",
                    f"PDOP={pdop:g}, while sqrt(HDOP²+VDOP²)={expected:g}; absolute difference={residual:g}.",
                    "C6", record.line_number, residual, tolerance,
                    "Confirm that PDOP, HDOP and VDOP columns/record fields were decoded from the same observation epoch and units."
                ))
        checks["dop_consistency"] = {
            "evaluated": evaluated,
            "median_abs_residual": float(np.median(residuals)) if residuals else None,
            "max_abs_residual": max(residuals) if residuals else None,
        }

    def _check_positions(self, dataset: GeodeticDataset, findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        position_records = dataset.records_for("66", "68")
        valid_positions: list[tuple[float, float]] = []
        duplicate_keys: dict[tuple[float, float], list[int]] = {}
        invalid = 0
        for record in position_records:
            try:
                lat = float(record.values.get("latitude_deg"))
                lon = float(record.values.get("longitude_deg"))
            except (TypeError, ValueError):
                invalid += 1
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                invalid += 1
                findings.append(GeodeticFinding(
                    "POSITION_RANGE", "FAIL", "Invalid geographic coordinate",
                    f"Latitude/longitude is outside valid geographic bounds: {lat}, {lon}.", record.record_id, record.line_number,
                    observed=f"{lat}, {lon}", suggested_action="Confirm angular units, hemisphere/sign convention and coordinate-system export settings.",
                ))
                continue
            valid_positions.append((lat, lon))
            key = (round(lat, 10), round(lon, 10))
            duplicate_keys.setdefault(key, []).append(record.line_number)
            for precision_key, label in (("horizontal_precision_m", "Horizontal precision"), ("vertical_precision_m", "Vertical precision")):
                if precision_key not in record.values:
                    continue
                try:
                    precision = float(record.values[precision_key])
                except (TypeError, ValueError):
                    continue
                if precision < 0:
                    findings.append(GeodeticFinding(
                        f"NEGATIVE_{precision_key.upper()}", "FAIL", f"Invalid {label.lower()}",
                        f"{label} is negative ({precision:g} m).", record.record_id, record.line_number, precision,
                        suggested_action="Verify the survey-controller export and precision field mapping.",
                    ))
                limit = self.thresholds.get(precision_key)
                if limit is not None and precision > limit:
                    findings.append(GeodeticFinding(
                        f"{precision_key.upper()}_LIMIT", "WARN", f"{label} above screening criterion",
                        f"{label} {precision:g} m exceeds configured screening value {limit:g} m.",
                        record.record_id, record.line_number, precision, limit,
                        "Review occupation quality and apply the governing project/control-survey specification.",
                    ))
        duplicates = {key: lines for key, lines in duplicate_keys.items() if len(lines) > 1}
        if duplicates:
            findings.append(GeodeticFinding(
                "DUPLICATE_COORDINATES", "INFO", "Repeated coordinates detected",
                f"{len(duplicates)} coordinate locations occur more than once. Repeats may be intentional control occupations and should be compared rather than silently removed.",
                suggested_action="Use repeated occupations for precision/repeatability assessment and verify point identifiers.",
            ))
        checks["positions"] = {"records": len(position_records), "valid": len(valid_positions), "invalid": invalid, "duplicate_locations": len(duplicates)}

    def _check_vectors(self, dataset: GeodeticDataset, findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        lengths: list[float] = []
        incomplete = 0
        for record in dataset.records_for("67"):
            try:
                dx = float(record.values["delta_x_m"]); dy = float(record.values["delta_y_m"]); dz = float(record.values["delta_z_m"])
            except (KeyError, TypeError, ValueError):
                incomplete += 1
                continue
            length = float(np.sqrt(dx * dx + dy * dy + dz * dz))
            lengths.append(length)
            if not np.isfinite(length):
                findings.append(GeodeticFinding("VECTOR_NONFINITE", "FAIL", "Invalid GPS vector", "A GPS vector contains non-finite components.", "67", record.line_number))
        checks["vectors"] = {
            "count": len(lengths), "incomplete": incomplete,
            "length_min_m": min(lengths) if lengths else None,
            "length_median_m": float(np.median(lengths)) if lengths else None,
            "length_max_m": max(lengths) if lengths else None,
        }

    def _check_gps_time(self, dataset: GeodeticDataset, findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        intervals: list[tuple[int, float, float, float | None]] = []
        for record in dataset.records_for("C6"):
            values = record.values
            try:
                sw = int(float(values["start_gps_week"])); st = float(values["start_gps_time_s"])
                ew = int(float(values.get("end_gps_week", sw))); et = float(values["end_gps_time_s"])
            except (KeyError, TypeError, ValueError):
                continue
            start_abs = sw * 604800.0 + st
            end_abs = ew * 604800.0 + et
            declared = None
            try:
                declared = float(values.get("delta_time_s"))
            except (TypeError, ValueError):
                pass
            intervals.append((record.line_number, start_abs, end_abs, declared))
            duration = end_abs - start_abs
            if duration < 0:
                findings.append(GeodeticFinding(
                    "NEGATIVE_GPS_INTERVAL", "FAIL", "GPS end time precedes start time",
                    f"Computed GPS interval is {duration:g} s.", "C6", record.line_number, duration,
                    suggested_action="Check GPS week rollover/time fields and the controller export.",
                ))
            if declared is not None and np.isfinite(declared) and abs(duration - declared) > max(0.05, abs(duration) * 0.01):
                findings.append(GeodeticFinding(
                    "GPS_DELTA_MISMATCH", "WARN", "Declared delta time differs from GPS timestamps",
                    f"Computed interval {duration:g} s differs from declared delta {declared:g} s.",
                    "C6", record.line_number, declared, duration,
                    "Confirm time units, GPS week rollover and export-field mapping.",
                ))
        starts = np.asarray([item[1] for item in intervals], dtype=float)
        if starts.size > 1 and np.any(np.diff(starts) < 0):
            findings.append(GeodeticFinding(
                "GPS_TIME_NONMONOTONIC", "WARN", "GPS observation time is non-monotonic",
                "C6 observations are not in chronological order.", record_id="C6",
                suggested_action="Sort only for analysis; preserve source order and verify controller logging/merge chronology.",
            ))
        checks["gps_time"] = {"complete_intervals": len(intervals), "monotonic": bool(starts.size < 2 or np.all(np.diff(starts) >= 0))}

    def _check_survey_settings(self, dataset: GeodeticDataset, findings: list[GeodeticFinding], checks: dict[str, Any]) -> None:
        elevation_masks = dataset.numeric_series(("56", "57"), "elevation_mask_deg")
        elevation_masks = elevation_masks[np.isfinite(elevation_masks)]
        pdop_masks = dataset.numeric_series(("56", "57"), "pdop_mask")
        pdop_masks = pdop_masks[np.isfinite(pdop_masks)]
        if elevation_masks.size and np.any((elevation_masks < 0) | (elevation_masks > 45)):
            findings.append(GeodeticFinding(
                "ELEVATION_MASK_RANGE", "WARN", "Unusual GNSS elevation mask",
                f"Recorded elevation mask range is {np.min(elevation_masks):g}–{np.max(elevation_masks):g}°. Values outside 0–45° require review.",
                record_id="56/57", suggested_action="Verify field-controller satellite mask settings and project GNSS procedure.",
            ))
        if pdop_masks.size and np.any(pdop_masks <= 0):
            findings.append(GeodeticFinding(
                "PDOP_MASK_INVALID", "FAIL", "Invalid PDOP mask", "A recorded PDOP mask is zero or negative.", record_id="56/57"
            ))
        antenna_heights = dataset.numeric_series(("56", "57"), "antenna_height_m")
        antenna_heights = antenna_heights[np.isfinite(antenna_heights)]
        if antenna_heights.size and np.any(antenna_heights <= 0):
            findings.append(GeodeticFinding(
                "ANTENNA_HEIGHT_NONPOSITIVE", "FAIL", "Invalid antenna height",
                "A recorded antenna height is zero or negative, which can directly bias derived elevations.", record_id="56/57",
                suggested_action="Verify antenna reference point, measurement method (vertical/slant) and entered antenna height before accepting elevations."
            ))
        checks["survey_settings"] = {
            "elevation_mask_deg": elevation_masks.tolist(), "pdop_mask": pdop_masks.tolist(),
            "antenna_height_m": antenna_heights.tolist(),
        }
