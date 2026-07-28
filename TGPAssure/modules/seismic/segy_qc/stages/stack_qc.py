from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    error_result,
    get_reader_and_index,
    make_finding,
    read_gather,
    sample_semblance,
    select_gather_groups,
    stage_result,
    threshold,
)


class StackQCStage(QCStage):
    """Generate bounded brute stacks and evaluate SNR, coherence and amplitude consistency."""

    STAGE_NAME = "StackQC"

    @staticmethod
    def _snr_db(stack: np.ndarray, gather: np.ndarray) -> float:
        signal_power = float(np.mean(np.square(stack)))
        residual = gather - stack[None, :]
        noise_power = float(np.mean(np.square(residual)))
        return float(10.0 * np.log10(max(signal_power, np.finfo(float).eps) / max(noise_power, np.finfo(float).eps)))

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            reader, index = get_reader_and_index(context)
            snr_min_db = threshold(context, "snr_min_db", 6.0)
            coherence_min = threshold(context, "stack_coherence_min", 0.35)
            amplitude_variation_max = threshold(context, "amplitude_variation_max_pct", 40.0)

            source_gathers = context.get("nmo_corrected_gathers") or []
            if not source_gathers:
                groups, _ = select_gather_groups(index, min_fold=3, max_gathers=16, max_traces_per_gather=64)
                source_gathers = []
                for key, indices in groups:
                    gather = read_gather(reader, index, key, indices, max_samples=1800)
                    source_gathers.append(
                        {
                            "gather_key": key,
                            "trace_indices": gather.trace_indices,
                            "offsets_m": gather.offsets_m,
                            "dt_ms": gather.dt_ms,
                            "data": gather.raw,
                            "normalized": gather.normalized,
                            "evaluation_mode": "input_gather",
                        }
                    )

            if not source_gathers:
                findings.append(
                    make_finding(
                        "STACK_GATHERS_UNAVAILABLE",
                        QCSeverity.WARNING,
                        "Brute-stack QC could not be performed because no pre-stack gathers with usable fold were found.",
                        category="stack",
                        title="No gathers available for stack QC",
                        suggested_action="Provide NMO-corrected CMP gathers or a pre-stack SEG-Y with populated CDP and offset headers.",
                    )
                )
                metrics = {
                    "brute_stack_count": 0,
                    "snr_median_db": 0.0,
                    "stack_coherence_median": 0.0,
                    "amplitude_variation_pct": 0.0,
                }
                context["brute_stacks"] = []
                context["stack_qc"] = {"available": False, "metrics": metrics}
                return stage_result(self.STAGE_NAME, metrics, findings)

            brute_stacks: List[Dict[str, Any]] = []
            snr_values: List[float] = []
            coherence_values: List[float] = []
            stack_rms_values: List[float] = []
            low_snr_windows = 0
            total_windows = 0
            per_gather: List[Dict[str, Any]] = []

            for source in source_gathers:
                data = np.asarray(source.get("data"), dtype=np.float64)
                normalized = np.asarray(source.get("normalized"), dtype=np.float64)
                if data.ndim != 2 or data.shape[0] < 2 or data.shape[1] < 8:
                    continue
                if normalized.shape != data.shape:
                    demeaned = data - np.mean(data, axis=1, keepdims=True)
                    rms = np.sqrt(np.mean(np.square(demeaned), axis=1, keepdims=True))
                    normalized = np.divide(
                        demeaned,
                        np.maximum(rms, np.finfo(float).eps),
                        out=np.zeros_like(demeaned),
                        where=rms > np.finfo(float).eps,
                    )
                stack = np.mean(data, axis=0)
                normalized_stack = np.mean(normalized, axis=0)
                snr_db = self._snr_db(normalized_stack, normalized)
                coherence_curve = sample_semblance(normalized, smoothing_samples=11)
                coherence = float(np.median(coherence_curve)) if coherence_curve.size else 0.0
                stack_rms = float(np.sqrt(np.mean(np.square(stack))))

                windows = min(12, max(1, stack.size // 64))
                edges = np.linspace(0, stack.size, windows + 1, dtype=int)
                gather_low_windows = 0
                window_snr: List[float] = []
                for window_index in range(windows):
                    start, end = int(edges[window_index]), int(edges[window_index + 1])
                    if end - start < 8:
                        continue
                    value = self._snr_db(normalized_stack[start:end], normalized[:, start:end])
                    window_snr.append(value)
                    total_windows += 1
                    if value < snr_min_db:
                        low_snr_windows += 1
                        gather_low_windows += 1

                snr_values.append(snr_db)
                coherence_values.append(coherence)
                stack_rms_values.append(stack_rms)
                key = str(source.get("gather_key", f"GATHER:{len(brute_stacks) + 1}"))
                per_gather.append(
                    {
                        "gather_key": key,
                        "trace_count": int(data.shape[0]),
                        "sample_count": int(data.shape[1]),
                        "snr_db": snr_db,
                        "coherence_median": coherence,
                        "stack_rms": stack_rms,
                        "low_snr_window_count": gather_low_windows,
                        "window_snr_min_db": float(np.min(window_snr)) if window_snr else snr_db,
                        "input_mode": source.get("evaluation_mode", "unknown"),
                    }
                )
                brute_stacks.append(
                    {
                        "gather_key": key,
                        "stack": stack,
                        "normalized_stack": normalized_stack,
                        "dt_ms": float(source.get("dt_ms", 1.0)),
                        "trace_count": int(data.shape[0]),
                        "snr_db": snr_db,
                        "coherence": coherence,
                    }
                )

            if not brute_stacks:
                raise ValueError("No valid gather arrays were available for brute stacking")

            snr_array = np.asarray(snr_values, dtype=np.float64)
            coherence_array = np.asarray(coherence_values, dtype=np.float64)
            rms_array = np.asarray(stack_rms_values, dtype=np.float64)
            snr_median = float(np.median(snr_array))
            coherence_median = float(np.median(coherence_array))
            rms_mean = float(np.mean(rms_array))
            amplitude_variation = float(100.0 * np.std(rms_array) / max(abs(rms_mean), np.finfo(float).eps))
            low_snr_zone_pct = 100.0 * low_snr_windows / max(1, total_windows)

            low_snr_gathers = int(np.count_nonzero(snr_array < snr_min_db))
            if snr_median < snr_min_db:
                findings.append(
                    make_finding(
                        "STACK_LOW_SNR",
                        QCSeverity.ERROR,
                        f"Median brute-stack SNR is {snr_median:.2f} dB, below the required {snr_min_db:.2f} dB.",
                        category="stack",
                        title="Stack SNR below tolerance",
                        metric_name="snr_median_db",
                        observed_value=snr_median,
                        expected_min=snr_min_db,
                        unit="dB",
                        suggested_action="Review residual statics, NMO velocities, mutes, noise attenuation, trace weighting and polarity before final stacking.",
                        context={"low_snr_gather_count": low_snr_gathers},
                    )
                )
            elif low_snr_gathers:
                findings.append(
                    make_finding(
                        "STACK_LOCAL_LOW_SNR",
                        QCSeverity.WARNING,
                        f"{low_snr_gathers} brute stacks fall below {snr_min_db:.2f} dB even though the dataset median passes.",
                        category="stack",
                        title="Localized low-SNR stacks",
                        metric_name="low_snr_gather_count",
                        observed_value=float(low_snr_gathers),
                        expected_max=0.0,
                        unit="gathers",
                        suggested_action="Inspect the affected CMP ranges for missing fold, coherent noise, statics errors or aggressive mutes.",
                    )
                )

            if coherence_median < coherence_min:
                findings.append(
                    make_finding(
                        "STACK_LOW_COHERENCE",
                        QCSeverity.ERROR,
                        f"Median stack coherence is {coherence_median:.3f}, below the required {coherence_min:.3f}.",
                        category="stack",
                        title="Low pre-stack coherence",
                        metric_name="stack_coherence_median",
                        observed_value=coherence_median,
                        expected_min=coherence_min,
                        unit="ratio",
                        suggested_action="Review gather alignment, residual moveout, statics, phase consistency and noise attenuation.",
                    )
                )

            if amplitude_variation > amplitude_variation_max:
                severity = QCSeverity.ERROR if amplitude_variation > amplitude_variation_max * 1.5 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "STACK_AMPLITUDE_VARIATION",
                        severity,
                        f"Brute-stack RMS varies by {amplitude_variation:.1f}%, exceeding {amplitude_variation_max:.1f}%.",
                        category="stack",
                        title="Stack amplitude inconsistency",
                        metric_name="amplitude_variation_pct",
                        observed_value=amplitude_variation,
                        expected_max=amplitude_variation_max,
                        unit="%",
                        suggested_action="Check surface-consistent scaling, fold normalization, gain recovery, mute consistency and anomalous high-energy zones.",
                    )
                )

            if low_snr_zone_pct > 20.0:
                findings.append(
                    make_finding(
                        "STACK_LOW_SNR_ZONES",
                        QCSeverity.WARNING,
                        f"{low_snr_zone_pct:.1f}% of stack time windows are below the SNR threshold.",
                        category="stack",
                        title="Low-SNR time zones detected",
                        metric_name="low_snr_zone_pct",
                        observed_value=low_snr_zone_pct,
                        expected_max=20.0,
                        unit="%",
                        suggested_action="Review time-variant noise attenuation and signal-preserving processing in the affected intervals.",
                    )
                )

            metrics = {
                "brute_stack_count": len(brute_stacks),
                "snr_min_db": float(np.min(snr_array)),
                "snr_max_db": float(np.max(snr_array)),
                "snr_median_db": snr_median,
                "low_snr_gather_count": low_snr_gathers,
                "low_snr_zone_pct": low_snr_zone_pct,
                "stack_coherence_min": float(np.min(coherence_array)),
                "stack_coherence_median": coherence_median,
                "stack_rms_min": float(np.min(rms_array)),
                "stack_rms_max": float(np.max(rms_array)),
                "amplitude_variation_pct": amplitude_variation,
                "per_gather": per_gather,
            }
            context["brute_stacks"] = brute_stacks
            context["stack_qc"] = {"available": True, "metrics": metrics}
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "STACK_QC_EXCEPTION", exc)
