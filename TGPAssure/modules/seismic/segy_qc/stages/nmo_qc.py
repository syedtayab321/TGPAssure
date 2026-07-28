from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    error_result,
    fft_lag_samples,
    get_reader_and_index,
    make_finding,
    nmo_correct,
    read_gather,
    sample_semblance,
    stage_result,
    threshold,
)


class NMOQCStage(QCStage):
    """Validate NMO correction using gather flatness and residual moveout."""

    STAGE_NAME = "NMOQC"

    @staticmethod
    def _residual_shifts(gather: np.ndarray, dt_ms: float, max_lag_ms: float) -> tuple[np.ndarray, np.ndarray]:
        reference = np.median(gather, axis=0)
        max_lag_samples = max(1, int(round(max_lag_ms / max(dt_ms, 1e-9))))
        shifts = np.zeros(gather.shape[0], dtype=np.float64)
        correlations = np.zeros(gather.shape[0], dtype=np.float64)
        for trace_index in range(gather.shape[0]):
            lag, correlation = fft_lag_samples(gather[trace_index], reference, max_lag_samples)
            shifts[trace_index] = float(lag) * dt_ms
            correlations[trace_index] = correlation
        return shifts, correlations

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            reader, index = get_reader_and_index(context)
            velocity_functions = context.get("velocity_functions") or []
            residual_max_ms = threshold(context, "residual_moveout_max_ms", 12.0)
            flatness_min = threshold(context, "flatness_ratio_min", 0.75)
            stretch_max_pct = threshold(context, "nmo_stretch_max_pct", 30.0)

            if not velocity_functions:
                findings.append(
                    make_finding(
                        "NMO_VELOCITY_UNAVAILABLE",
                        QCSeverity.WARNING,
                        "NMO QC could not be executed because no valid velocity functions are available from the velocity stage.",
                        category="nmo",
                        title="Velocity functions unavailable for NMO QC",
                        suggested_action="Run velocity QC on pre-stack CMP gathers or supply validated RMS velocity functions before evaluating NMO.",
                    )
                )
                metrics = {
                    "analysed_gather_count": 0,
                    "flatness_ratio": 0.0,
                    "residual_moveout_p95_ms": 0.0,
                    "nmo_stretch_p95_pct": 0.0,
                }
                context["nmo_corrected_gathers"] = []
                context["nmo_qc"] = {"available": False, "metrics": metrics}
                return stage_result(self.STAGE_NAME, metrics, findings)

            corrected_gathers: List[Dict[str, Any]] = []
            all_residuals: List[float] = []
            all_correlations: List[float] = []
            all_stretches: List[float] = []
            gather_flatness: List[float] = []
            per_gather: List[Dict[str, Any]] = []
            over_corrected = 0
            under_corrected = 0
            already_corrected = 0

            correlation_window_ms = max(3.0 * residual_max_ms, 40.0)
            for function in velocity_functions:
                indices = np.asarray(function.get("trace_indices", []), dtype=np.int64)
                if indices.size < 3:
                    continue
                key = str(function.get("gather_key", "UNKNOWN"))
                gather = read_gather(reader, index, key, indices, max_samples=1600)
                corrected_raw, stretches = nmo_correct(gather.raw, gather.offsets_m, gather.dt_ms, function)
                corrected_norm, _ = nmo_correct(gather.normalized, gather.offsets_m, gather.dt_ms, function)

                raw_shifts, raw_corr = self._residual_shifts(gather.normalized, gather.dt_ms, correlation_window_ms)
                corrected_shifts, corrected_corr = self._residual_shifts(corrected_norm, gather.dt_ms, correlation_window_ms)
                raw_flatness = float(np.mean(np.abs(raw_shifts) <= residual_max_ms))
                corrected_flatness = float(np.mean(np.abs(corrected_shifts) <= residual_max_ms))

                if raw_flatness > corrected_flatness + 0.05:
                    selected_raw = gather.raw
                    selected_norm = gather.normalized
                    selected_shifts = raw_shifts
                    selected_corr = raw_corr
                    selected_mode = "input_already_nmo_corrected"
                    flatness = raw_flatness
                    already_corrected += 1
                else:
                    selected_raw = corrected_raw
                    selected_norm = corrected_norm
                    selected_shifts = corrected_shifts
                    selected_corr = corrected_corr
                    selected_mode = "nmo_applied_from_velocity_qc"
                    flatness = corrected_flatness

                offset_squared = np.square(np.abs(gather.offsets_m))
                if np.ptp(offset_squared) > 0 and selected_shifts.size >= 3:
                    slope, intercept = np.polyfit(offset_squared, selected_shifts, 1)
                    edge_trend_ms = float(slope * np.ptp(offset_squared))
                else:
                    slope, intercept, edge_trend_ms = 0.0, 0.0, 0.0
                if edge_trend_ms > residual_max_ms * 0.5:
                    under_corrected += 1
                    pattern = "under-correction"
                elif edge_trend_ms < -residual_max_ms * 0.5:
                    over_corrected += 1
                    pattern = "over-correction"
                else:
                    pattern = "flat"

                valid_stretch = stretches[np.isfinite(stretches) & (stretches >= 0)]
                stretch_p95 = float(np.percentile(valid_stretch, 95)) if valid_stretch.size else 0.0
                coherence = sample_semblance(selected_norm)
                coherence_median = float(np.median(coherence)) if coherence.size else 0.0

                all_residuals.extend(selected_shifts.tolist())
                all_correlations.extend(selected_corr.tolist())
                all_stretches.extend(valid_stretch.tolist())
                gather_flatness.append(flatness)
                per_gather.append(
                    {
                        "gather_key": key,
                        "trace_count": int(indices.size),
                        "evaluation_mode": selected_mode,
                        "raw_flatness_ratio": raw_flatness,
                        "corrected_flatness_ratio": corrected_flatness,
                        "selected_flatness_ratio": flatness,
                        "residual_moveout_p95_ms": float(np.percentile(np.abs(selected_shifts), 95)),
                        "stretch_p95_pct": stretch_p95,
                        "moveout_pattern": pattern,
                        "edge_moveout_trend_ms": edge_trend_ms,
                        "coherence_median": coherence_median,
                    }
                )
                corrected_gathers.append(
                    {
                        "gather_key": key,
                        "trace_indices": gather.trace_indices,
                        "offsets_m": gather.offsets_m,
                        "dt_ms": gather.dt_ms,
                        "data": selected_raw,
                        "normalized": selected_norm,
                        "residual_shifts_ms": selected_shifts,
                        "correlations": selected_corr,
                        "stretch_pct": stretches,
                        "evaluation_mode": selected_mode,
                        "flatness_ratio": flatness,
                    }
                )

            if not corrected_gathers:
                findings.append(
                    make_finding(
                        "NMO_GATHERS_UNAVAILABLE",
                        QCSeverity.WARNING,
                        "Velocity functions were present, but none referenced at least three readable traces for NMO evaluation.",
                        category="nmo",
                        title="No matching gathers for NMO QC",
                        suggested_action="Ensure each velocity function retains its gather_key and trace_indices from the velocity analysis stage.",
                    )
                )
                metrics = {
                    "analysed_gather_count": 0,
                    "flatness_ratio": 0.0,
                    "residual_moveout_p95_ms": 0.0,
                    "nmo_stretch_p95_pct": 0.0,
                }
                context["nmo_corrected_gathers"] = []
                context["nmo_qc"] = {"available": False, "metrics": metrics}
                return stage_result(self.STAGE_NAME, metrics, findings)

            residuals = np.asarray(all_residuals, dtype=np.float64)
            correlations = np.asarray(all_correlations, dtype=np.float64)
            stretches = np.asarray(all_stretches, dtype=np.float64)
            flatness_ratio = float(np.mean(gather_flatness))
            residual_p95 = float(np.percentile(np.abs(residuals), 95)) if residuals.size else 0.0
            residual_max = float(np.max(np.abs(residuals))) if residuals.size else 0.0
            stretch_p95 = float(np.percentile(stretches, 95)) if stretches.size else 0.0

            if residual_p95 > residual_max_ms:
                findings.append(
                    make_finding(
                        "NMO_RESIDUAL_MOVEOUT",
                        QCSeverity.ERROR,
                        f"The 95th-percentile residual moveout is {residual_p95:.2f} ms, exceeding {residual_max_ms:.2f} ms.",
                        category="nmo",
                        title="Residual moveout exceeds tolerance",
                        metric_name="residual_moveout_p95_ms",
                        observed_value=residual_p95,
                        expected_max=residual_max_ms,
                        unit="ms",
                        suggested_action="Repick RMS velocities, review anisotropy, residual statics and offset geometry, then repeat NMO correction.",
                    )
                )

            if flatness_ratio < flatness_min:
                severity = QCSeverity.ERROR if flatness_ratio < flatness_min * 0.75 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "NMO_LOW_FLATNESS",
                        severity,
                        f"Only {flatness_ratio * 100.0:.1f}% of evaluated traces are flat within ±{residual_max_ms:.1f} ms; the minimum required ratio is {flatness_min * 100.0:.1f}%.",
                        category="nmo",
                        title="CMP gathers are not sufficiently flat",
                        metric_name="flatness_ratio",
                        observed_value=flatness_ratio,
                        expected_min=flatness_min,
                        unit="ratio",
                        suggested_action="Inspect residual moveout by offset and time, update velocity functions, and verify that NMO was not applied twice.",
                    )
                )

            if stretch_p95 > stretch_max_pct:
                severity = QCSeverity.ERROR if stretch_p95 > stretch_max_pct * 1.5 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "NMO_EXCESSIVE_STRETCH",
                        severity,
                        f"The 95th-percentile NMO stretch is {stretch_p95:.1f}%, exceeding {stretch_max_pct:.1f}%.",
                        category="nmo",
                        title="Excessive NMO stretch",
                        metric_name="nmo_stretch_p95_pct",
                        observed_value=stretch_p95,
                        expected_max=stretch_max_pct,
                        unit="%",
                        suggested_action="Apply an appropriate stretch mute, review shallow velocities and offset limits, and confirm the sample-time datum.",
                    )
                )

            pattern_count = over_corrected + under_corrected
            if pattern_count:
                findings.append(
                    make_finding(
                        "NMO_SYSTEMATIC_PATTERN",
                        QCSeverity.WARNING,
                        f"Systematic moveout trends were detected in {pattern_count} gathers: {under_corrected} under-corrected and {over_corrected} over-corrected.",
                        category="nmo",
                        title="Systematic NMO correction pattern",
                        metric_name="patterned_gather_count",
                        observed_value=float(pattern_count),
                        expected_max=0.0,
                        unit="gathers",
                        suggested_action="Review velocity trends against offset-squared residual moveout and repick the affected time intervals.",
                    )
                )

            metrics = {
                "analysed_gather_count": len(corrected_gathers),
                "analysed_trace_count": int(residuals.size),
                "flatness_ratio": flatness_ratio,
                "residual_moveout_median_ms": float(np.median(residuals)) if residuals.size else 0.0,
                "residual_moveout_p95_ms": residual_p95,
                "residual_moveout_max_abs_ms": residual_max,
                "median_cross_correlation": float(np.median(correlations)) if correlations.size else 0.0,
                "nmo_stretch_p95_pct": stretch_p95,
                "already_corrected_gather_count": already_corrected,
                "under_corrected_gather_count": under_corrected,
                "over_corrected_gather_count": over_corrected,
                "per_gather": per_gather,
            }
            context["nmo_corrected_gathers"] = corrected_gathers
            context["nmo_qc"] = {"available": True, "metrics": metrics}
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "NMO_QC_EXCEPTION", exc)
