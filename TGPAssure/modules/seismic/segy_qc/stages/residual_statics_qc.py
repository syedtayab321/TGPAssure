from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    error_result,
    fft_lag_samples,
    get_reader_and_index,
    make_finding,
    read_gather,
    robust_center_sigma,
    robust_outlier_mask,
    select_gather_groups,
    stage_result,
    threshold,
)


class ResidualStaticsQCStage(QCStage):
    """Estimate residual trace statics from within-gather cross-correlation."""

    STAGE_NAME = "ResidualStaticsQC"

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            reader, index = get_reader_and_index(context)
            max_static_ms = threshold(context, "residual_static_max_ms", 12.0)
            outlier_factor = threshold(context, "residual_static_outlier_factor", 4.5)
            groups, group_type = select_gather_groups(index, min_fold=3, max_gathers=14, max_traces_per_gather=56)

            if not groups:
                findings.append(
                    make_finding(
                        "RESIDUAL_STATICS_GATHERS_UNAVAILABLE",
                        QCSeverity.WARNING,
                        "Residual statics could not be estimated because the SEG-Y does not contain repeated CDP/bin/field-record gathers with usable fold.",
                        category="residual_statics",
                        title="No gathers available for residual statics",
                        suggested_action="Provide pre-stack data sorted by CDP with populated offset and ensemble headers, or load a residual-statics table from processing.",
                        context={"group_type_attempted": group_type},
                    )
                )
                metrics = {
                    "analysed_gather_count": 0,
                    "analysed_trace_count": 0,
                    "residual_static_max_abs_ms": 0.0,
                    "residual_static_p95_abs_ms": 0.0,
                    "outlier_count": 0,
                }
                context["residual_statics"] = {"available": False, "metrics": metrics}
                return stage_result(self.STAGE_NAME, metrics, findings)

            shifts: List[float] = []
            correlations: List[float] = []
            trace_indices: List[int] = []
            gather_keys: List[str] = []
            per_gather: List[Dict[str, Any]] = []

            correlation_window_ms = max(2.0 * max_static_ms, 40.0)
            for key, indices in groups:
                gather = read_gather(reader, index, key, indices, max_samples=1800)
                reference = np.median(gather.normalized, axis=0)
                max_lag_samples = max(1, int(round(correlation_window_ms / max(gather.dt_ms, 1e-9))))
                gather_shifts: List[float] = []
                gather_corr: List[float] = []
                for row, trace_index in enumerate(gather.trace_indices):
                    lag_samples, correlation = fft_lag_samples(
                        gather.normalized[row],
                        reference,
                        max_lag_samples=max_lag_samples,
                    )
                    shift_ms = float(lag_samples) * gather.dt_ms
                    shifts.append(shift_ms)
                    correlations.append(correlation)
                    trace_indices.append(int(trace_index))
                    gather_keys.append(key)
                    gather_shifts.append(shift_ms)
                    gather_corr.append(correlation)
                per_gather.append(
                    {
                        "gather_key": key,
                        "trace_count": int(gather.trace_indices.size),
                        "median_shift_ms": float(np.median(gather_shifts)),
                        "p95_abs_shift_ms": float(np.percentile(np.abs(gather_shifts), 95)),
                        "median_correlation": float(np.median(gather_corr)),
                    }
                )

            shift_array = np.asarray(shifts, dtype=np.float64)
            correlation_array = np.asarray(correlations, dtype=np.float64)
            trace_array = np.asarray(trace_indices, dtype=np.int64)
            outlier_mask = robust_outlier_mask(shift_array, outlier_factor)
            magnitude_mask = np.abs(shift_array) > max_static_ms
            outlier_indices = np.flatnonzero(outlier_mask)
            magnitude_indices = np.flatnonzero(magnitude_mask)
            center, sigma = robust_center_sigma(shift_array)
            max_abs = float(np.max(np.abs(shift_array))) if shift_array.size else 0.0
            p95_abs = float(np.percentile(np.abs(shift_array), 95)) if shift_array.size else 0.0

            if magnitude_indices.size:
                affected = trace_array[magnitude_indices]
                findings.append(
                    make_finding(
                        "RESIDUAL_STATIC_MAGNITUDE",
                        QCSeverity.ERROR,
                        f"{magnitude_indices.size:,} traces exceed the maximum residual static magnitude of {max_static_ms:.2f} ms; the observed maximum is {max_abs:.2f} ms.",
                        category="residual_statics",
                        title="Residual statics exceed tolerance",
                        metric_name="residual_static_max_abs_ms",
                        observed_value=max_abs,
                        expected_max=max_static_ms,
                        unit="ms",
                        location_ref=f"Trace {int(affected[0]) + 1}",
                        suggested_action="Revisit surface-consistent residual statics, correlation windows, reference traces, and datum/uphole corrections before stacking.",
                        context={
                            "affected_trace_count": int(affected.size),
                            "affected_trace_indices": (affected[:200] + 1).tolist(),
                        },
                    )
                )

            if outlier_indices.size:
                affected = trace_array[outlier_indices]
                severity = QCSeverity.ERROR if outlier_indices.size / max(1, shift_array.size) > 0.05 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "RESIDUAL_STATIC_MAD_OUTLIERS",
                        severity,
                        f"{outlier_indices.size:,} cross-correlation statics are robust-MAD outliers using factor {outlier_factor:.2f}.",
                        category="residual_statics",
                        title="Residual-static outliers detected",
                        metric_name="residual_static_outlier_count",
                        observed_value=float(outlier_indices.size),
                        expected_max=0.0,
                        unit="traces",
                        location_ref=f"Trace {int(affected[0]) + 1}",
                        suggested_action="Inspect the affected gathers for cycle skips, weak events, noise bursts, polarity reversals, or incorrect geometry before accepting the statics solution.",
                        context={
                            "median_ms": center,
                            "robust_sigma_ms": sigma,
                            "affected_trace_indices": (affected[:200] + 1).tolist(),
                        },
                    )
                )

            low_correlation = np.flatnonzero(correlation_array < 0.25)
            if low_correlation.size:
                findings.append(
                    make_finding(
                        "RESIDUAL_STATIC_LOW_CORRELATION",
                        QCSeverity.WARNING,
                        f"{low_correlation.size:,} trace-to-reference correlations are below 0.25, reducing confidence in the estimated residual shifts.",
                        category="residual_statics",
                        title="Low residual-static correlation confidence",
                        metric_name="low_correlation_trace_count",
                        observed_value=float(low_correlation.size),
                        expected_max=0.0,
                        unit="traces",
                        suggested_action="Use event-windowed correlation, improve noise attenuation, and verify polarity before deriving final residual statics.",
                        context={"median_correlation": float(np.median(correlation_array))},
                    )
                )

            metrics = {
                "group_type": group_type,
                "analysed_gather_count": len(groups),
                "analysed_trace_count": int(shift_array.size),
                "residual_static_median_ms": center,
                "residual_static_robust_sigma_ms": sigma,
                "residual_static_max_abs_ms": max_abs,
                "residual_static_p95_abs_ms": p95_abs,
                "residual_static_outlier_count": int(outlier_indices.size),
                "threshold_exceedance_count": int(magnitude_indices.size),
                "median_cross_correlation": float(np.median(correlation_array)) if correlation_array.size else 0.0,
                "per_gather": per_gather,
            }
            context["residual_statics"] = {
                "available": True,
                "trace_indices": trace_array,
                "gather_keys": gather_keys,
                "shifts_ms": shift_array,
                "correlations": correlation_array,
                "outlier_mask": outlier_mask,
                "metrics": metrics,
            }
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "RESIDUAL_STATICS_QC_EXCEPTION", exc)
