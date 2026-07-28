from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Callable

import numpy as np

from modules.electrical.constants import DEFAULT_QC_THRESHOLDS, ElectricalMethod, METHOD_REQUIRED_FIELDS
from modules.electrical.models import ElectricalDataset, ElectricalQcResult, QcFinding, QcStageResult
from modules.electrical.processing import ElectricalProcessingEngine


class ElectricalQcEngine:
    def __init__(self, thresholds: dict[str, float] | None = None) -> None:
        self.thresholds = dict(DEFAULT_QC_THRESHOLDS)
        if thresholds:
            self.thresholds.update({key: float(value) for key, value in thresholds.items()})
        self.processing = ElectricalProcessingEngine()

    def run(
        self,
        dataset: ElectricalDataset,
        *,
        profile_name: str = "Electrical Standard QC",
        progress: Callable[[int, str], None] | None = None,
    ) -> ElectricalQcResult:
        started = time.perf_counter()
        data = self.processing.derive_standard_fields(dataset)
        stages: list[QcStageResult] = []
        stage_functions = [
            self._schema_stage,
            self._geometry_stage,
            self._signal_stage,
            self._resistivity_stage,
            self._reciprocity_repeat_stage,
            self._method_specific_stage,
            self._summary_stage,
        ]
        for index, function in enumerate(stage_functions):
            if progress:
                progress(int(index / len(stage_functions) * 95), function.__name__.replace("_", " ").title())
            stage_start = time.perf_counter()
            stage = function(data)
            stage.duration_ms = int((time.perf_counter() - stage_start) * 1000)
            stages.append(stage)
        score = float(np.mean([stage.score for stage in stages])) if stages else 0.0
        status = self._overall_status(stages, score)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if progress:
            progress(100, "Electrical QC complete")
        return ElectricalQcResult(
            dataset=data,
            stages=stages,
            score=score,
            status=status,
            profile_name=profile_name,
            thresholds=dict(self.thresholds),
            duration_ms=duration_ms,
        )

    def _schema_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        required_groups = METHOD_REQUIRED_FIELDS.get(dataset.method, ())
        missing_groups = [group for group in required_groups if not any(dataset.has(field) for field in group)]
        if missing_groups:
            for i, group in enumerate(missing_groups, start=1):
                findings.append(QcFinding(
                    code=f"ELEC-SCHEMA-{i:02d}", severity="error", stage_key="schema",
                    title="Required measurement field missing",
                    message="At least one of these fields is required for the selected method: " + ", ".join(group),
                    suggested_action="Check the selected method or import an instrument export containing the required columns.",
                ))
        lengths = {len(values) for values in dataset.columns.values()}
        if len(lengths) > 1:
            findings.append(QcFinding(
                code="ELEC-SCHEMA-LENGTH", severity="critical", stage_key="schema",
                title="Column length mismatch", message="Imported columns do not contain the same number of records.",
                suggested_action="Re-export the source table and verify delimiters/merged cells before QC.",
            ))
        empty = dataset.record_count == 0
        if empty:
            findings.append(QcFinding(
                code="ELEC-SCHEMA-EMPTY", severity="critical", stage_key="schema",
                title="Empty dataset", message="No electrical measurement records are available.",
                suggested_action="Select a valid survey export.",
            ))
        error_count = sum(f.severity in {"error", "critical"} for f in findings)
        score = max(0.0, 100.0 - error_count * 35.0)
        status = "fail" if error_count else "pass"
        return QcStageResult("schema", "File / Schema Integrity", status, score,
                             "Schema is complete." if not findings else f"{len(findings)} schema issue(s) found.",
                             {"record_count": dataset.record_count, "recognized_fields": len(dataset.columns), "missing_field_groups": len(missing_groups)}, findings)

    def _geometry_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if {"a", "b", "m", "n"}.issubset(dataset.columns):
            arrays = {name: dataset.numeric(name) for name in ("a", "b", "m", "n")}
            finite = np.logical_and.reduce([np.isfinite(values) for values in arrays.values()])
            duplicate = finite & (
                (arrays["a"] == arrays["b"]) | (arrays["m"] == arrays["n"]) |
                (arrays["a"] == arrays["m"]) | (arrays["a"] == arrays["n"]) |
                (arrays["b"] == arrays["m"]) | (arrays["b"] == arrays["n"])
            )
            invalid_factor = np.zeros(dataset.record_count, dtype=bool)
            if dataset.has("geometry_factor_m"):
                factor = dataset.numeric("geometry_factor_m")
                invalid_factor = ~np.isfinite(factor) | (np.abs(factor) < 1e-12)
            metrics.update({
                "finite_geometry_pct": _pct(np.count_nonzero(finite), dataset.record_count),
                "duplicate_electrode_rows": int(np.count_nonzero(duplicate)),
                "invalid_geometry_factor_rows": int(np.count_nonzero(invalid_factor)),
            })
            if dataset.has("array_type"):
                array_types = [value for value in dataset.text("array_type") if value]
                counts = Counter(array_types)
                metrics["array_type_count"] = len(counts)
                metrics["array_types"] = ", ".join(f"{name}: {count}" for name, count in counts.most_common(8))
            bad_indices = np.flatnonzero(duplicate | invalid_factor)[:25]
            for index in bad_indices:
                findings.append(QcFinding(
                    code="ELEC-GEOM-ELECTRODES", severity="error", stage_key="geometry",
                    title="Invalid electrode geometry", message=f"Row {index + 1} has coincident/invalid A-B-M-N geometry.",
                    suggested_action="Verify electrode numbers/positions and array sequence before inversion.", row_index=int(index),
                ))
            missing_pct = 100.0 - float(metrics["finite_geometry_pct"])
            if missing_pct > 0:
                findings.append(QcFinding(
                    code="ELEC-GEOM-MISSING", severity="warning" if missing_pct < 5 else "error", stage_key="geometry",
                    title="Incomplete electrode geometry", message=f"{missing_pct:.2f}% of rows have missing A/B/M/N positions.",
                    suggested_action="Recover electrode positions from field sequence/controller export.", observed_value=missing_pct, unit="%",
                ))
        elif dataset.method == ElectricalMethod.VES and dataset.has("ab2_m"):
            ab2 = dataset.numeric("ab2_m")
            invalid = ~np.isfinite(ab2) | (ab2 <= 0)
            metrics["invalid_ab2_rows"] = int(np.count_nonzero(invalid))
            if np.any(invalid):
                findings.append(QcFinding(
                    code="ELEC-VES-AB2", severity="error", stage_key="geometry",
                    title="Invalid AB/2 spacing", message=f"{np.count_nonzero(invalid)} VES readings have missing/non-positive AB/2.",
                    suggested_action="Correct sounding electrode spacings before curve QC.",
                ))
            if dataset.has("mn2_m"):
                mn2 = dataset.numeric("mn2_m")
                invalid_mn = ~np.isfinite(mn2) | (mn2 <= 0) | (np.isfinite(ab2) & (mn2 >= ab2))
                metrics["invalid_mn2_rows"] = int(np.count_nonzero(invalid_mn))
                if np.any(invalid_mn):
                    findings.append(QcFinding(
                        code="ELEC-VES-MN2", severity="warning", stage_key="geometry",
                        title="Invalid or suspicious MN/2 spacing",
                        message=f"{np.count_nonzero(invalid_mn)} VES readings have missing/non-positive MN/2 or MN/2 not smaller than AB/2.",
                        suggested_action="Verify potential-electrode spacing and sounding field notes before curve interpretation.",
                    ))
        else:
            metrics["geometry_mode"] = "station/profile only"
        status, score = _stage_status_score(findings)
        return QcStageResult("geometry", "Electrode Geometry / Position QC", status, score,
                             "Electrode geometry is usable." if not findings else f"{len(findings)} geometry finding(s).", metrics, findings)

    def _signal_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("current_ma"):
            current = np.abs(dataset.numeric("current_ma"))
            low = np.isfinite(current) & (current < self.thresholds["min_current_ma"])
            metrics["low_current_rows"] = int(np.count_nonzero(low))
            if np.any(low):
                findings.append(QcFinding(
                    "ELEC-SIGNAL-CURRENT", "warning", "signal", "Low injected current",
                    f"{np.count_nonzero(low)} readings are below the configured {self.thresholds['min_current_ma']:g} mA current threshold.",
                    "Improve current-electrode contact, verify transmitter output/power and repeat weak readings.",
                    expected_min=self.thresholds["min_current_ma"], unit="mA",
                ))
        if dataset.has("voltage_mv"):
            voltage = np.abs(dataset.numeric("voltage_mv"))
            low = np.isfinite(voltage) & (voltage < self.thresholds["min_abs_voltage_mv"])
            metrics["low_voltage_rows"] = int(np.count_nonzero(low))
            if np.any(low):
                findings.append(QcFinding(
                    "ELEC-SIGNAL-VOLTAGE", "warning", "signal", "Very low receiver voltage",
                    f"{np.count_nonzero(low)} readings fall below the configured receiver-voltage threshold.",
                    "Increase signal level/stacking where safe and check potential-electrode contact/noise.",
                    expected_min=self.thresholds["min_abs_voltage_mv"], unit="mV",
                ))
        if dataset.has("contact_resistance_ohm"):
            contact = dataset.numeric("contact_resistance_ohm")
            high = np.isfinite(contact) & (contact > self.thresholds["contact_resistance_warn_ohm"])
            metrics["contact_resistance_median_ohm"] = _finite_median(contact)
            metrics["high_contact_resistance_rows"] = int(np.count_nonzero(high))
            if np.any(high):
                findings.append(QcFinding(
                    "ELEC-SIGNAL-CONTACT", "warning", "signal", "High electrode/ground contact resistance",
                    f"{np.count_nonzero(high)} readings exceed the configured {self.thresholds['contact_resistance_warn_ohm']:.0f} Ω warning level.",
                    "Improve electrode contact (depth/moisture/parallel stakes as appropriate), then repeat affected readings.",
                    expected_max=self.thresholds["contact_resistance_warn_ohm"], unit="ohm",
                ))
        if dataset.has("stack_std_pct"):
            deviation = dataset.numeric("stack_std_pct")
            high = np.isfinite(deviation) & (deviation > self.thresholds["stack_std_warn_pct"])
            metrics["stack_std_median_pct"] = _finite_median(deviation)
            metrics["high_stack_deviation_rows"] = int(np.count_nonzero(high))
            if np.any(high):
                findings.append(QcFinding(
                    "ELEC-SIGNAL-STACK", "warning", "signal", "High stacking deviation / repeat noise",
                    f"{np.count_nonzero(high)} readings exceed {self.thresholds['stack_std_warn_pct']:g}% stacking deviation.",
                    "Increase stacking/repeat measurements and investigate cultural/electrode noise.",
                    expected_max=self.thresholds["stack_std_warn_pct"], unit="%",
                ))
        status, score = _stage_status_score(findings)
        return QcStageResult("signal", "Signal / Contact / Stacking QC", status, score,
                             "Signal diagnostics are within configured limits." if not findings else f"{len(findings)} signal-quality finding(s).", metrics, findings)

    def _resistivity_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("apparent_resistivity_ohm_m"):
            rho = dataset.numeric("apparent_resistivity_ohm_m")
            invalid = ~np.isfinite(rho)
            nonpositive = np.isfinite(rho) & (rho <= 0)
            outliers = self.processing.robust_outlier_mask(rho, self.thresholds["outlier_mad_z"], log_positive=True)
            valid = rho[np.isfinite(rho) & (rho > 0)]
            metrics.update({
                "valid_resistivity_pct": _pct(valid.size, dataset.record_count),
                "nonpositive_rows": int(np.count_nonzero(nonpositive)),
                "missing_rows": int(np.count_nonzero(invalid)),
                "robust_outlier_rows": int(np.count_nonzero(outliers)),
                "rho_median_ohm_m": float(np.median(valid)) if valid.size else float("nan"),
            })
            if np.any(nonpositive):
                findings.append(QcFinding(
                    "ELEC-RHO-NONPOS", "error", "resistivity", "Non-positive apparent resistivity",
                    f"{np.count_nonzero(nonpositive)} readings have zero/negative apparent resistivity.",
                    "Check polarity, electrode geometry, current/voltage signs and instrument export conventions before inversion.",
                ))
            if np.any(invalid):
                findings.append(QcFinding(
                    "ELEC-RHO-MISSING", "warning", "resistivity", "Missing apparent resistivity",
                    f"{np.count_nonzero(invalid)} readings could not provide apparent resistivity.",
                    "Recover current/voltage/geometry fields or remove unrecoverable readings with an audit trail.",
                ))
            if np.any(outliers):
                findings.append(QcFinding(
                    "ELEC-RHO-OUTLIER", "warning", "resistivity", "Robust resistivity outliers",
                    f"{np.count_nonzero(outliers)} readings are extreme relative to the dataset on a log-resistivity MAD test.",
                    "Review rather than automatically delete; extreme values may be geology or acquisition error.",
                ))
        else:
            findings.append(QcFinding(
                "ELEC-RHO-ABSENT", "info", "resistivity", "Apparent resistivity not available",
                "This dataset/method does not currently contain or permit calculation of apparent resistivity.",
                "For active resistivity/IP surveys, include current, voltage and electrode geometry or exported apparent resistivity.",
            ))
        status, score = _stage_status_score(findings)
        return QcStageResult("resistivity", "Apparent Resistivity QC", status, score,
                             "Apparent resistivity passed automated checks." if not findings else f"{len(findings)} resistivity finding(s).", metrics, findings)

    def _reciprocity_repeat_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("reciprocal_error_pct"):
            error = dataset.numeric("reciprocal_error_pct")
            finite = error[np.isfinite(error)]
            warn = np.isfinite(error) & (error > self.thresholds["reciprocal_warn_pct"])
            fail = np.isfinite(error) & (error > self.thresholds["reciprocal_fail_pct"])
            metrics.update({
                "reciprocal_pair_count": int(dataset.metadata.get("reciprocal_pair_count", 0)),
                "reciprocal_error_median_pct": float(np.median(finite)) if finite.size else float("nan"),
                "reciprocal_error_p95_pct": float(np.percentile(finite, 95)) if finite.size else float("nan"),
                "reciprocal_warn_rows": int(np.count_nonzero(warn)),
                "reciprocal_fail_rows": int(np.count_nonzero(fail)),
            })
            if np.any(fail):
                findings.append(QcFinding(
                    "ELEC-RECIP-FAIL", "error", "reciprocity", "High normal–reciprocal mismatch",
                    f"{np.count_nonzero(fail)} reciprocal readings exceed {self.thresholds['reciprocal_fail_pct']:g}% error.",
                    "Reject/repeat only after checking electrode contact, switching, leakage and temporal/cultural noise.",
                    expected_max=self.thresholds["reciprocal_fail_pct"], unit="%",
                ))
            elif np.any(warn):
                findings.append(QcFinding(
                    "ELEC-RECIP-WARN", "warning", "reciprocity", "Elevated reciprocal error",
                    f"{np.count_nonzero(warn)} reciprocal readings exceed {self.thresholds['reciprocal_warn_pct']:g}% error.",
                    "Review reciprocal pairs and use the error distribution to weight/filter inversion data.",
                    expected_max=self.thresholds["reciprocal_warn_pct"], unit="%",
                ))
        else:
            metrics["reciprocal_pair_count"] = 0
            findings.append(QcFinding(
                "ELEC-RECIP-NONE", "info", "reciprocity", "No reciprocal pairs identified",
                "Normal–reciprocal error could not be calculated from the imported sequence.",
                "Acquire reciprocal measurements where survey design/time permits, especially for ERT/IP error characterization.",
            ))

        repeat_metrics, repeat_findings = self._repeat_consistency(dataset)
        metrics.update(repeat_metrics)
        findings.extend(repeat_findings)
        status, score = _stage_status_score(findings)
        return QcStageResult("reciprocity", "Reciprocity / Repeatability QC", status, score,
                             "Reciprocity/repeatability checks completed.", metrics, findings)

    def _repeat_consistency(self, dataset: ElectricalDataset) -> tuple[dict[str, float | int], list[QcFinding]]:
        if not dataset.has("repeat_id"):
            return {"repeat_group_count": 0}, []
        key_values = dataset.text("repeat_id")
        target_name = next((name for name in ("apparent_resistivity_ohm_m", "chargeability_mv_v", "sp_mv") if dataset.has(name)), None)
        if not target_name:
            return {"repeat_group_count": 0}, []
        target = dataset.numeric(target_name)
        groups: dict[str, list[float]] = defaultdict(list)
        for key, value in zip(key_values, target):
            if key and np.isfinite(value):
                groups[key].append(float(value))
        errors: list[float] = []
        for values in groups.values():
            if len(values) < 2:
                continue
            mean_abs = np.mean(np.abs(values))
            if mean_abs > 1e-12:
                errors.append(100.0 * (max(values) - min(values)) / mean_abs)
        metrics: dict[str, float | int] = {"repeat_group_count": len(errors)}
        findings: list[QcFinding] = []
        if errors:
            metrics["repeat_spread_median_pct"] = float(np.median(errors))
            bad = sum(error > self.thresholds["repeat_warn_pct"] for error in errors)
            metrics["repeat_groups_above_limit"] = int(bad)
            if bad:
                findings.append(QcFinding(
                    "ELEC-REPEAT-SPREAD", "warning", "reciprocity", "Repeat measurements are inconsistent",
                    f"{bad} repeat groups exceed {self.thresholds['repeat_warn_pct']:g}% relative spread.",
                    "Review repeat stations/readings and investigate changing contact/noise/field conditions.",
                    expected_max=self.thresholds["repeat_warn_pct"], unit="%",
                ))
        return metrics, findings

    def _method_specific_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        if dataset.method == ElectricalMethod.VES:
            return self._ves_stage(dataset)
        if dataset.method == ElectricalMethod.TDIP:
            return self._tdip_stage(dataset)
        if dataset.method in {ElectricalMethod.FDIP, ElectricalMethod.SIP}:
            return self._spectral_stage(dataset)
        if dataset.method == ElectricalMethod.SP:
            return self._sp_stage(dataset)
        if dataset.method in {ElectricalMethod.MALM, ElectricalMethod.EQUIPOTENTIAL}:
            return self._potential_mapping_stage(dataset)
        if dataset.method == ElectricalMethod.TELLURIC:
            return self._telluric_stage(dataset)
        return self._ert_profile_stage(dataset)

    def _ves_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("ab2_m"):
            ab2 = dataset.numeric("ab2_m")
            finite = ab2[np.isfinite(ab2) & (ab2 > 0)]
            metrics["ab2_unique_count"] = int(len(np.unique(finite)))
            if finite.size > 1:
                decreases = int(np.count_nonzero(np.diff(finite) < 0))
                metrics["ab2_order_decreases"] = decreases
                if decreases:
                    findings.append(QcFinding(
                        "ELEC-VES-ORDER", "warning", "method_specific", "VES AB/2 sequence is not monotonic",
                        f"AB/2 decreases {decreases} time(s) in acquisition order.",
                        "Verify sounding sequence/order or sort by AB/2 only for curve display while preserving original acquisition order.",
                    ))
        if dataset.has("apparent_resistivity_ohm_m") and dataset.has("ab2_m"):
            rho = dataset.numeric("apparent_resistivity_ohm_m")
            ab2 = dataset.numeric("ab2_m")
            valid = np.isfinite(rho) & (rho > 0) & np.isfinite(ab2) & (ab2 > 0)
            if np.count_nonzero(valid) >= 5:
                order = np.argsort(ab2[valid])
                logrho = np.log10(rho[valid][order])
                roughness = np.abs(np.diff(logrho, n=2)) if len(logrho) >= 3 else np.array([])
                metrics["curve_roughness_median"] = float(np.median(roughness)) if roughness.size else 0.0
                spikes = int(np.count_nonzero(roughness > 0.5))
                metrics["curve_sharp_break_count"] = spikes
                if spikes:
                    findings.append(QcFinding(
                        "ELEC-VES-CURVE", "warning", "method_specific", "Abrupt VES curve changes",
                        f"{spikes} strong second-difference curve breaks were detected on log apparent resistivity.",
                        "Check field notes, MN/2 overlap points and repeat suspect spacings before interpretation/inversion.",
                    ))
        if dataset.has("apparent_resistivity_ohm_m") and dataset.has("ab2_m"):
            rho = dataset.numeric("apparent_resistivity_ohm_m")
            ab2 = dataset.numeric("ab2_m")
            groups: dict[float, list[float]] = defaultdict(list)
            for spacing, value in zip(ab2, rho):
                if np.isfinite(spacing) and spacing > 0 and np.isfinite(value) and value > 0:
                    groups[round(float(spacing), 6)].append(float(value))
            overlap_spreads = []
            for values in groups.values():
                if len(values) < 2:
                    continue
                mean = float(np.mean(np.abs(values)))
                if mean > 1e-12:
                    overlap_spreads.append(100.0 * (max(values) - min(values)) / mean)
            metrics["repeated_ab2_group_count"] = len(overlap_spreads)
            if overlap_spreads:
                metrics["repeated_ab2_spread_median_pct"] = float(np.median(overlap_spreads))
                bad = sum(value > self.thresholds["repeat_warn_pct"] for value in overlap_spreads)
                metrics["repeated_ab2_groups_above_limit"] = int(bad)
                if bad:
                    findings.append(QcFinding(
                        "ELEC-VES-OVERLAP", "warning", "method_specific", "VES repeated/overlap spacings disagree",
                        f"{bad} repeated AB/2 spacing group(s) exceed {self.thresholds['repeat_warn_pct']:g}% spread.",
                        "Review overlap/repeat readings, MN/2 changes, electrode contact and temporal noise before curve interpretation.",
                        expected_max=self.thresholds["repeat_warn_pct"], unit="%",
                    ))
        status, score = _stage_status_score(findings)
        return QcStageResult("method_specific", "VES Curve / Sounding QC", status, score,
                             "VES-specific checks completed.", metrics, findings)

    def _tdip_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("chargeability_mv_v"):
            chargeability = dataset.numeric("chargeability_mv_v")
            finite = chargeability[np.isfinite(chargeability)]
            negative = np.isfinite(chargeability) & (chargeability < self.thresholds["tdip_negative_warn_mv_v"])
            extreme = np.isfinite(chargeability) & (np.abs(chargeability) > self.thresholds["tdip_extreme_warn_mv_v"])
            metrics.update({
                "chargeability_median_mv_v": float(np.median(finite)) if finite.size else float("nan"),
                "negative_chargeability_rows": int(np.count_nonzero(negative)),
                "extreme_chargeability_rows": int(np.count_nonzero(extreme)),
            })
            if np.any(negative):
                findings.append(QcFinding(
                    "ELEC-TDIP-NEG", "warning", "method_specific", "Negative apparent chargeability",
                    f"{np.count_nonzero(negative)} readings have negative chargeability under the imported sign convention.",
                    "Check polarity, SP cancellation, timing windows and instrument convention before filtering.", unit="mV/V",
                ))
            if np.any(extreme):
                findings.append(QcFinding(
                    "ELEC-TDIP-EXTREME", "warning", "method_specific", "Extreme chargeability values",
                    f"{np.count_nonzero(extreme)} readings exceed the configured absolute chargeability screening limit.",
                    "Inspect raw decay curves and receiver saturation/coupling before accepting the values.",
                    expected_max=self.thresholds["tdip_extreme_warn_mv_v"], unit="mV/V",
                ))
        decay_columns = sorted(name for name in dataset.columns if name.startswith("decay_") or name.startswith("window_"))
        metrics["decay_window_count"] = len(decay_columns)
        if len(decay_columns) >= 3:
            matrix = np.vstack([dataset.numeric(name) for name in decay_columns]).T
            valid_rows = np.all(np.isfinite(matrix), axis=1)
            nondecay = np.zeros(dataset.record_count, dtype=bool)
            if np.any(valid_rows):
                abs_matrix = np.abs(matrix[valid_rows])
                nondecay_valid = np.any(np.diff(abs_matrix, axis=1) > np.maximum(abs_matrix[:, :-1] * 0.25, 1e-9), axis=1)
                nondecay[np.flatnonzero(valid_rows)] = nondecay_valid
            metrics["non_monotonic_decay_rows"] = int(np.count_nonzero(nondecay))
            if np.any(nondecay):
                findings.append(QcFinding(
                    "ELEC-TDIP-DECAY", "warning", "method_specific", "Irregular TDIP decay windows",
                    f"{np.count_nonzero(nondecay)} records show large increases between successive absolute decay windows.",
                    "Inspect full-wave/decay data for EM coupling, noise, timing or polarity problems.",
                ))
        status, score = _stage_status_score(findings)
        return QcStageResult("method_specific", "Time-Domain IP / Decay QC", status, score,
                             "TDIP-specific checks completed.", metrics, findings)

    def _spectral_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("frequency_hz"):
            frequency = dataset.numeric("frequency_hz")
            valid = frequency[np.isfinite(frequency) & (frequency > 0)]
            invalid = ~np.isfinite(frequency) | (frequency <= 0)
            unique = np.unique(valid)
            metrics.update({
                "valid_frequency_pct": _pct(valid.size, dataset.record_count),
                "unique_frequency_count": int(unique.size),
                "frequency_min_hz": float(np.min(valid)) if valid.size else float("nan"),
                "frequency_max_hz": float(np.max(valid)) if valid.size else float("nan"),
            })
            if np.any(invalid):
                findings.append(QcFinding(
                    "ELEC-SIP-FREQ", "error", "method_specific", "Invalid spectral frequency",
                    f"{np.count_nonzero(invalid)} records have missing/non-positive frequency.",
                    "Correct frequency metadata before spectral plotting/model fitting.",
                ))
            if dataset.method == ElectricalMethod.SIP and unique.size < 3:
                findings.append(QcFinding(
                    "ELEC-SIP-COVERAGE", "warning", "method_specific", "Limited SIP frequency coverage",
                    f"Only {unique.size} unique valid frequencies were identified.",
                    "Confirm the complete spectral export; multiple frequencies are needed to characterize dispersion.",
                ))
        if dataset.has("phase_mrad"):
            phase = dataset.numeric("phase_mrad")
            extreme = np.isfinite(phase) & (np.abs(phase) > self.thresholds["sip_abs_phase_warn_mrad"])
            metrics["phase_median_mrad"] = _finite_median(phase)
            metrics["phase_extreme_rows"] = int(np.count_nonzero(extreme))
            if np.any(extreme):
                findings.append(QcFinding(
                    "ELEC-SIP-PHASE", "warning", "method_specific", "Extreme spectral phase values",
                    f"{np.count_nonzero(extreme)} values exceed the configured absolute phase screening limit.",
                    "Check phase units/sign convention, coupling and instrument synchronization before interpretation.",
                    expected_max=self.thresholds["sip_abs_phase_warn_mrad"], unit="mrad",
                ))
        status, score = _stage_status_score(findings)
        return QcStageResult("method_specific", "FDIP / SIP Frequency-Phase QC", status, score,
                             "Spectral/frequency-domain checks completed.", metrics, findings)

    def _sp_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        sp_name = "sp_corrected_mv" if dataset.has("sp_corrected_mv") else "sp_mv" if dataset.has("sp_mv") else "voltage_mv" if dataset.has("voltage_mv") else None
        if sp_name and dataset.has(sp_name):
            sp = dataset.numeric(sp_name)
            finite = sp[np.isfinite(sp)]
            metrics.update({
                "sp_median_mv": float(np.median(finite)) if finite.size else float("nan"),
                "sp_range_mv": float(np.ptp(finite)) if finite.size else float("nan"),
            })
        if dataset.has("is_base") and sp_name and dataset.has(sp_name):
            base = dataset.numeric(sp_name)[dataset.columns["is_base"].astype(bool)]
            base = base[np.isfinite(base)]
            metrics["base_reading_count"] = int(base.size)
            if base.size >= 2:
                closure = float(base[-1] - base[0])
                metrics["base_closure_mv"] = closure
                if abs(closure) > self.thresholds["sp_drift_warn_mv"]:
                    findings.append(QcFinding(
                        "ELEC-SP-DRIFT", "warning", "method_specific", "SP base/reference drift",
                        f"Base closure is {closure:.3f} mV, exceeding the configured ±{self.thresholds['sp_drift_warn_mv']:g} mV screening level.",
                        "Apply documented drift correction using repeated non-polarizing base readings and review electrode stability.",
                        observed_value=closure, unit="mV",
                    ))
            elif base.size == 1:
                findings.append(QcFinding(
                    "ELEC-SP-BASE", "info", "method_specific", "Only one SP base reading",
                    "Drift/closure cannot be quantified from a single base/reference reading.",
                    "Repeat the base station periodically and at survey closure.",
                ))
        else:
            findings.append(QcFinding(
                "ELEC-SP-NOBASE", "info", "method_specific", "No explicit SP base/reference flag",
                "Automated base drift/closure QC is unavailable.",
                "Include base/reference readings in the export (is_base/reference field) for drift QC.",
            ))
        status, score = _stage_status_score(findings)
        return QcStageResult("method_specific", "Self-Potential Drift / Closure QC", status, score,
                             "SP-specific checks completed.", metrics, findings)

    def _potential_mapping_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int | str] = {}
        value_name = "voltage_mv" if dataset.has("voltage_mv") else "sp_mv" if dataset.has("sp_mv") else None
        if value_name:
            values = dataset.numeric(value_name)
            finite = values[np.isfinite(values)]
            metrics["valid_potential_pct"] = _pct(finite.size, dataset.record_count)
            metrics["potential_median_mv"] = float(np.median(finite)) if finite.size else float("nan")
            metrics["potential_range_mv"] = float(np.ptp(finite)) if finite.size else float("nan")
            outliers = self.processing.robust_outlier_mask(values, z_limit=self.thresholds["outlier_mad_z"])
            metrics["robust_potential_outlier_rows"] = int(np.count_nonzero(outliers))
            if np.any(outliers):
                findings.append(QcFinding(
                    "ELEC-POTMAP-OUTLIER", "warning", "method_specific", "Potential-map robust outliers",
                    f"{np.count_nonzero(outliers)} potential readings are extreme on the configured robust MAD screen.",
                    "Review electrode/reference stability, source geometry, cultural leakage and field notes before deleting any point.",
                ))
        if dataset.has("source_id"):
            sources = [v for v in dataset.text("source_id") if v]
            counts = Counter(sources)
            metrics["source_count"] = len(counts)
            metrics["largest_source_record_count"] = max(counts.values(), default=0)
            if len(counts) > 1:
                metrics["sources"] = ", ".join(sorted(counts)[:10])
        elif dataset.method == ElectricalMethod.MALM:
            findings.append(QcFinding(
                "ELEC-MALM-SOURCE", "error", "method_specific", "MALM source identifier missing",
                "The energized body/source electrode cannot be tracked across measurements.",
                "Include source electrode/body identifier and fixed return/reference information in the import.",
            ))
        else:
            findings.append(QcFinding(
                "ELEC-EQUIP-SOURCE", "info", "method_specific", "No explicit energized-source identifier",
                "A source identifier is not mandatory for generic equipotential mapping, but it improves survey traceability when current is injected.",
                "Include source/reference identifiers when the potential map is tied to an energized electrode or body.",
            ))
        if not (dataset.has("easting") and dataset.has("northing")):
            findings.append(QcFinding(
                "ELEC-POTMAP-XY", "warning", "method_specific", "Potential-map coordinates missing",
                "Potential/equipotential mapping is limited without station coordinates.",
                "Import easting/northing (or projected X/Y) for potential/equipotential mapping.",
            ))
        status, score = _stage_status_score(findings)
        title = "Mise-à-la-Masse Source / Mapping QC" if dataset.method == ElectricalMethod.MALM else "Equipotential / Potential Mapping QC"
        message = "MALM-specific checks completed." if dataset.method == ElectricalMethod.MALM else "Equipotential mapping checks completed."
        return QcStageResult("method_specific", title, status, score, message, metrics, findings)

    def _telluric_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int | str] = {}
        signal_fields = [name for name in (
            "electric_field_mv_km", "electric_field_x_mv_km", "electric_field_y_mv_km", "voltage_mv", "sp_mv"
        ) if dataset.has(name)]
        metrics["signal_component_count"] = len(signal_fields)
        for value_name in signal_fields:
            values = dataset.numeric(value_name)
            finite = values[np.isfinite(values)]
            metrics[f"{value_name}_valid_pct"] = _pct(finite.size, dataset.record_count)
            metrics[f"{value_name}_median"] = float(np.median(finite)) if finite.size else float("nan")
            metrics[f"{value_name}_range"] = float(np.ptp(finite)) if finite.size else float("nan")
            outliers = self.processing.robust_outlier_mask(values, z_limit=self.thresholds["outlier_mad_z"])
            metrics[f"{value_name}_robust_outlier_rows"] = int(np.count_nonzero(outliers))
        if dataset.has("timestamp"):
            timestamps = dataset.text("timestamp")
            missing_time = int(np.count_nonzero(np.asarray([not value.strip() for value in timestamps], dtype=bool)))
            metrics["missing_timestamp_rows"] = missing_time
            if missing_time:
                findings.append(QcFinding(
                    "ELEC-TELLURIC-TIME-GAPS", "warning", "method_specific", "Telluric timestamp gaps",
                    f"{missing_time} record(s) have blank timestamps, limiting temporal/reference QC.",
                    "Recover acquisition timestamps and verify synchronization before temporal interpretation.",
                ))
        else:
            findings.append(QcFinding(
                "ELEC-TELLURIC-TIME", "warning", "method_specific", "Telluric timestamps missing",
                "Temporal coherence/drift and reference synchronization cannot be checked without timestamps.",
                "Include acquisition timestamps and reference-channel/station metadata for telluric QC.",
            ))
        if not dataset.has("repeat_id") and not dataset.has("is_base"):
            findings.append(QcFinding(
                "ELEC-TELLURIC-REF", "info", "method_specific", "No explicit telluric reference/repeat field",
                "Reference-station/repeat consistency cannot be quantified from the imported table.",
                "Include reference station/channel identifiers or repeats for temporal-noise QC.",
            ))
        status, score = _stage_status_score(findings)
        return QcStageResult("method_specific", "Telluric Reference / Temporal QC", status, score,
                             "Telluric-specific checks completed.", metrics, findings)

    def _ert_profile_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        findings: list[QcFinding] = []
        metrics: dict[str, float | int] = {}
        if dataset.has("line_id"):
            lines = [v for v in dataset.text("line_id") if v]
            metrics["line_count"] = len(set(lines))
        if dataset.has("pseudo_depth"):
            depth = dataset.numeric("pseudo_depth")
            finite = depth[np.isfinite(depth)]
            metrics["pseudo_depth_max"] = float(np.max(finite)) if finite.size else float("nan")
        if dataset.method == ElectricalMethod.ERT and not dataset.has("reciprocal_error_pct"):
            findings.append(QcFinding(
                "ELEC-ERT-RECIP", "info", "method_specific", "ERT sequence has no detected reciprocal pairs",
                "The dataset can still be processed, but direct reciprocal error characterization is unavailable.",
                "Include reciprocal measurements in future sequences where acquisition time allows.",
            ))
        status, score = _stage_status_score(findings)
        return QcStageResult("method_specific", "ERT / Profiling Survey QC", status, score,
                             "ERT/profile-specific checks completed.", metrics, findings)

    def _summary_stage(self, dataset: ElectricalDataset) -> QcStageResult:
        metrics = dataset.summary()
        return QcStageResult("summary", "QC Summary / Inversion Readiness", "pass", 100.0,
                             "Dataset summary generated. Automated QC supports, but does not replace, competent geophysical review or inversion diagnostics.", metrics, [])

    @staticmethod
    def _overall_status(stages: list[QcStageResult], score: float) -> str:
        statuses = {stage.status for stage in stages}
        if "fail" in statuses or score < 60:
            return "fail"
        if "warning" in statuses or score < 85:
            return "warning"
        return "pass"


def _stage_status_score(findings: list[QcFinding]) -> tuple[str, float]:
    severity_penalty = {"critical": 45.0, "error": 25.0, "warning": 8.0, "info": 0.0}
    penalty = min(100.0, sum(severity_penalty.get(finding.severity, 5.0) for finding in findings))
    score = max(0.0, 100.0 - penalty)
    if any(f.severity in {"critical", "error"} for f in findings):
        return "fail", score
    if any(f.severity == "warning" for f in findings):
        return "warning", score
    return "pass", score


def _pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 3) if total else 0.0


def _finite_median(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.median(finite)) if finite.size else float("nan")
