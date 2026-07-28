from __future__ import annotations

from typing import Any, Dict, List, Mapping

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    error_result,
    get_reader_and_index,
    make_finding,
    read_gather,
    select_gather_groups,
    smooth_velocity,
    stage_result,
    threshold,
    velocity_smoothness_metrics,
)


class VelocityQCStage(QCStage):
    """Estimate/validate RMS velocity functions from pre-stack CMP gathers."""

    STAGE_NAME = "VelocityQC"

    @staticmethod
    def _semblance_scan(
        gather: np.ndarray,
        offsets_m: np.ndarray,
        dt_ms: float,
        velocity_candidates: np.ndarray,
        sample_positions: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        trace_count, sample_count = gather.shape
        sample_axis = np.arange(sample_count, dtype=np.float64)
        dt_s = max(float(dt_ms) / 1000.0, np.finfo(float).eps)
        t0_s = sample_positions.astype(np.float64) * dt_s
        semblance = np.zeros((velocity_candidates.size, sample_positions.size), dtype=np.float64)

        for velocity_index, velocity in enumerate(velocity_candidates):
            input_times_s = np.sqrt(
                np.square(t0_s)[None, :]
                + np.square(offsets_m[:, None] / max(float(velocity), 1.0))
            )
            input_samples = input_times_s / dt_s
            sampled = np.zeros((trace_count, sample_positions.size), dtype=np.float64)
            for trace_index in range(trace_count):
                sampled[trace_index] = np.interp(
                    input_samples[trace_index],
                    sample_axis,
                    gather[trace_index],
                    left=0.0,
                    right=0.0,
                )
            numerator = np.square(np.sum(sampled, axis=0))
            denominator = trace_count * np.sum(np.square(sampled), axis=0) + np.finfo(float).eps
            semblance[velocity_index] = np.clip(numerator / denominator, 0.0, 1.0)

        best_indices = np.argmax(semblance, axis=0)
        best_velocities = velocity_candidates[best_indices]
        best_semblance = semblance[best_indices, np.arange(sample_positions.size)]
        return best_velocities.astype(np.float64), best_semblance.astype(np.float64)

    def _validate_provided_functions(
        self,
        functions: List[Mapping[str, Any]],
        velocity_min: float,
        velocity_max: float,
        semblance_min: float,
        smoothness_max: float,
    ) -> tuple[List[Dict[str, Any]], List[QCFinding]]:
        findings: List[QCFinding] = []
        validated: List[Dict[str, Any]] = []
        for ordinal, function in enumerate(functions):
            times = np.asarray(function.get("times_ms", []), dtype=np.float64)
            velocities = np.asarray(function.get("velocities_m_s", []), dtype=np.float64)
            semblance = np.asarray(function.get("semblance", np.ones_like(velocities)), dtype=np.float64)
            count = min(times.size, velocities.size, semblance.size)
            if count < 2:
                continue
            times = times[:count]
            velocities = velocities[:count]
            semblance = semblance[:count]
            validated.append(
                {
                    **dict(function),
                    "gather_key": str(function.get("gather_key", f"PROVIDED:{ordinal + 1}")),
                    "times_ms": times,
                    "velocities_m_s": velocities,
                    "semblance": semblance,
                    "source": "provided",
                }
            )
        if not validated:
            findings.append(
                make_finding(
                    "VELOCITY_FUNCTIONS_INVALID",
                    QCSeverity.ERROR,
                    "Velocity functions were supplied in the context, but none contained at least two valid time/velocity/semblance samples.",
                    category="velocity",
                    title="Invalid supplied velocity functions",
                    suggested_action="Provide velocity functions using times_ms, velocities_m_s, and optional semblance arrays of equal length.",
                )
            )
        return validated, findings

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            reader, index = get_reader_and_index(context)
            velocity_min = threshold(context, "velocity_min_m_s", 1200.0)
            velocity_max = threshold(context, "velocity_max_m_s", 6500.0)
            semblance_min = threshold(context, "semblance_min", 0.25)
            smoothness_max = threshold(context, "velocity_smoothness_max", 20.0)

            provided = context.get("provided_velocity_functions")
            velocity_functions: List[Dict[str, Any]] = []
            group_type = "PROVIDED"
            if isinstance(provided, list) and provided:
                velocity_functions, provided_findings = self._validate_provided_functions(
                    provided,
                    velocity_min,
                    velocity_max,
                    semblance_min,
                    smoothness_max,
                )
                findings.extend(provided_findings)
            else:
                groups, group_type = select_gather_groups(index, min_fold=4, max_gathers=12, max_traces_per_gather=48)
                if not groups:
                    findings.append(
                        make_finding(
                            "VELOCITY_GATHERS_UNAVAILABLE",
                            QCSeverity.WARNING,
                            "Velocity analysis could not be performed because no CMP/bin gathers with fold of at least four were found.",
                            category="velocity",
                            title="No gathers available for velocity QC",
                            suggested_action="Use pre-stack CMP-sorted SEG-Y with populated CDP and offset headers, or supply velocity functions through the processing context.",
                            context={"group_type_attempted": group_type},
                        )
                    )
                    metrics = {
                        "velocity_function_count": 0,
                        "analysed_gather_count": 0,
                        "velocity_min_m_s": 0.0,
                        "velocity_max_m_s": 0.0,
                        "semblance_median": 0.0,
                    }
                    context["velocity_functions"] = []
                    context["velocity_qc"] = {"available": False, "metrics": metrics}
                    return stage_result(self.STAGE_NAME, metrics, findings)

                scan_min = max(400.0, velocity_min * 0.70)
                scan_max = max(scan_min + 200.0, velocity_max * 1.20)
                velocity_candidates = np.linspace(scan_min, scan_max, 32, dtype=np.float64)

                for key, indices in groups:
                    gather = read_gather(reader, index, key, indices, max_samples=1400)
                    sample_count = gather.sample_count
                    start = max(2, int(round(80.0 / max(gather.dt_ms, 1e-9))))
                    stop = max(start + 1, int(sample_count * 0.92))
                    target_count = min(180, max(24, stop - start))
                    sample_positions = np.unique(np.linspace(start, stop - 1, target_count, dtype=int))
                    raw_velocity, best_semblance = self._semblance_scan(
                        gather.normalized,
                        gather.offsets_m,
                        gather.dt_ms,
                        velocity_candidates,
                        sample_positions,
                    )
                    smoothed_velocity = smooth_velocity(raw_velocity, window=7)
                    velocity_functions.append(
                        {
                            "gather_key": key,
                            "trace_indices": gather.trace_indices,
                            "offsets_m": gather.offsets_m,
                            "times_ms": sample_positions.astype(np.float64) * gather.dt_ms,
                            "velocities_m_s": smoothed_velocity,
                            "raw_velocities_m_s": raw_velocity,
                            "semblance": best_semblance,
                            "dt_ms": gather.dt_ms,
                            "source": "semblance_scan",
                        }
                    )

            all_velocities = np.concatenate(
                [np.asarray(item["velocities_m_s"], dtype=np.float64) for item in velocity_functions]
            ) if velocity_functions else np.array([], dtype=np.float64)
            all_semblance = np.concatenate(
                [np.asarray(item.get("semblance", []), dtype=np.float64) for item in velocity_functions]
            ) if velocity_functions else np.array([], dtype=np.float64)
            valid_velocity = all_velocities[np.isfinite(all_velocities)]
            valid_semblance = all_semblance[np.isfinite(all_semblance)]

            outside_mask = (valid_velocity < velocity_min) | (valid_velocity > velocity_max)
            outside_count = int(np.count_nonzero(outside_mask))
            if outside_count:
                findings.append(
                    make_finding(
                        "VELOCITY_OUTSIDE_RANGE",
                        QCSeverity.ERROR,
                        f"{outside_count:,} velocity picks fall outside the permitted range {velocity_min:.0f}-{velocity_max:.0f} m/s.",
                        category="velocity",
                        title="Velocity values outside profile range",
                        metric_name="velocity_outside_range_count",
                        observed_value=float(outside_count),
                        expected_max=0.0,
                        unit="picks",
                        suggested_action="Review velocity picking, anisotropy assumptions, statics, mute zones, and units before NMO or migration.",
                        context={
                            "observed_min_m_s": float(np.min(valid_velocity)) if valid_velocity.size else None,
                            "observed_max_m_s": float(np.max(valid_velocity)) if valid_velocity.size else None,
                        },
                    )
                )

            low_semblance_count = int(np.count_nonzero(valid_semblance < semblance_min))
            low_semblance_pct = 100.0 * low_semblance_count / max(1, valid_semblance.size)
            if low_semblance_count:
                severity = QCSeverity.ERROR if low_semblance_pct > 35.0 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "LOW_VELOCITY_SEMBLANCE",
                        severity,
                        f"{low_semblance_count:,} velocity picks ({low_semblance_pct:.1f}%) have semblance below {semblance_min:.2f}.",
                        category="velocity",
                        title="Weak velocity semblance",
                        metric_name="low_semblance_pct",
                        observed_value=low_semblance_pct,
                        expected_max=0.0,
                        unit="%",
                        suggested_action="Improve gather conditioning, statics, deconvolution and mute design, then repick velocities using interpretable reflection events.",
                    )
                )

            inversion_count = 0
            inversion_total = 0
            for function in velocity_functions:
                velocities = np.asarray(function["velocities_m_s"], dtype=np.float64)
                if velocities.size < 2:
                    continue
                changes = np.diff(velocities)
                significant = changes < -0.03 * np.maximum(velocities[:-1], 1.0)
                inversion_count += int(np.count_nonzero(significant))
                inversion_total += int(changes.size)
            inversion_pct = 100.0 * inversion_count / max(1, inversion_total)
            if inversion_count:
                severity = QCSeverity.ERROR if inversion_pct > 10.0 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "VELOCITY_INVERSIONS",
                        severity,
                        f"{inversion_count:,} significant velocity inversions were detected ({inversion_pct:.1f}% of adjacent picks).",
                        category="velocity",
                        title="Velocity inversions detected",
                        metric_name="velocity_inversion_pct",
                        observed_value=inversion_pct,
                        expected_max=0.0,
                        unit="%",
                        suggested_action="Confirm whether inversions are geologically justified; otherwise smooth or repick the velocity functions without suppressing real low-velocity zones.",
                    )
                )

            smoothness = velocity_smoothness_metrics(velocity_functions)
            if smoothness["velocity_step_p95_pct"] > smoothness_max:
                findings.append(
                    make_finding(
                        "VELOCITY_SMOOTHNESS",
                        QCSeverity.ERROR,
                        f"The 95th-percentile adjacent velocity change is {smoothness['velocity_step_p95_pct']:.1f}%, exceeding {smoothness_max:.1f}%.",
                        category="velocity",
                        title="Velocity functions are insufficiently smooth",
                        metric_name="velocity_step_p95_pct",
                        observed_value=smoothness["velocity_step_p95_pct"],
                        expected_max=smoothness_max,
                        unit="%",
                        suggested_action="Review isolated picks, cycle skips and lateral consistency; apply geologically constrained smoothing before NMO and migration.",
                    )
                )

            metrics = {
                "group_type": group_type,
                "velocity_function_count": len(velocity_functions),
                "velocity_pick_count": int(valid_velocity.size),
                "velocity_min_m_s": float(np.min(valid_velocity)) if valid_velocity.size else 0.0,
                "velocity_max_m_s": float(np.max(valid_velocity)) if valid_velocity.size else 0.0,
                "velocity_median_m_s": float(np.median(valid_velocity)) if valid_velocity.size else 0.0,
                "velocity_outside_range_count": outside_count,
                "semblance_min": float(np.min(valid_semblance)) if valid_semblance.size else 0.0,
                "semblance_median": float(np.median(valid_semblance)) if valid_semblance.size else 0.0,
                "low_semblance_count": low_semblance_count,
                "low_semblance_pct": low_semblance_pct,
                "velocity_inversion_count": inversion_count,
                "velocity_inversion_pct": inversion_pct,
                **smoothness,
                "functions": [
                    {
                        "gather_key": item["gather_key"],
                        "pick_count": int(np.asarray(item["velocities_m_s"]).size),
                        "velocity_min_m_s": float(np.min(item["velocities_m_s"])),
                        "velocity_max_m_s": float(np.max(item["velocities_m_s"])),
                        "semblance_median": float(np.median(item.get("semblance", [0.0]))),
                        "source": item.get("source", "unknown"),
                    }
                    for item in velocity_functions
                ],
            }
            context["velocity_functions"] = velocity_functions
            context["velocity_qc"] = {"available": bool(velocity_functions), "metrics": metrics}
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "VELOCITY_QC_EXCEPTION", exc)
