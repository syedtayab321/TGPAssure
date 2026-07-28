from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    analytic_attributes,
    error_result,
    get_reader_and_index,
    make_finding,
    section_from_context,
    stage_result,
    threshold,
    velocity_smoothness_metrics,
)


class MigrationQCStage(QCStage):
    """Screen migrated/post-stack sections for focusing, curvature and edge artifacts."""

    STAGE_NAME = "MigrationQC"

    @staticmethod
    def _bow_artifact_percentage(section: np.ndarray) -> tuple[float, int, int, float]:
        envelope = analytic_attributes(section, 1.0)["envelope"]
        trace_count, sample_count = envelope.shape
        if trace_count < 5 or sample_count < 32:
            return 0.0, 0, 0, 0.0
        x = np.linspace(-1.0, 1.0, trace_count, dtype=np.float64)
        window_count = min(24, max(6, sample_count // 80))
        edges = np.linspace(0, sample_count, window_count + 1, dtype=int)
        global_level = float(np.percentile(envelope, 70))
        artifact_windows = 0
        analysed_windows = 0
        bow_samples: List[float] = []
        for window_index in range(window_count):
            start, end = int(edges[window_index]), int(edges[window_index + 1])
            if end - start < 8:
                continue
            window = envelope[:, start:end]
            if float(np.percentile(window, 90)) <= global_level:
                continue
            picks = start + np.argmax(window, axis=1).astype(np.float64)
            weights = np.max(window, axis=1)
            valid = np.isfinite(picks) & np.isfinite(weights) & (weights > 0)
            if np.count_nonzero(valid) < 5:
                continue
            coefficients = np.polyfit(x[valid], picks[valid], 2, w=np.sqrt(weights[valid]))
            bow = abs(float(coefficients[0]))
            bow_samples.append(bow)
            analysed_windows += 1
            if bow > 3.0:
                artifact_windows += 1
        percentage = 100.0 * artifact_windows / max(1, analysed_windows)
        return percentage, artifact_windows, analysed_windows, float(np.percentile(bow_samples, 95)) if bow_samples else 0.0

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            get_reader_and_index(context)
            artifact_max_pct = threshold(context, "migration_artifact_max_pct", 8.0)
            velocity_smoothness_min = threshold(context, "velocity_smoothness_min", 70.0)
            focus_ratio_min = threshold(context, "migration_focus_ratio_min", 1.20)

            section, dt_ms, section_keys = section_from_context(context, max_traces=180, max_samples=1800)
            if section.shape[0] < 3 or section.shape[1] < 16:
                raise ValueError("Migration QC requires at least three traces and sixteen samples")

            demeaned = section - np.mean(section, axis=1, keepdims=True)
            trace_rms = np.sqrt(np.mean(np.square(demeaned), axis=1, keepdims=True))
            normalized = np.divide(
                demeaned,
                np.maximum(trace_rms, np.finfo(float).eps),
                out=np.zeros_like(demeaned),
                where=trace_rms > np.finfo(float).eps,
            )

            coherent = np.mean(normalized, axis=0)
            coherent_power = float(np.mean(np.square(coherent)))
            residual_power = float(np.mean(np.square(normalized - coherent[None, :])))
            focus_ratio = coherent_power / max(residual_power, np.finfo(float).eps)

            edge_width = max(1, int(round(normalized.shape[0] * 0.08)))
            edge = np.vstack((normalized[:edge_width], normalized[-edge_width:]))
            center_start = edge_width
            center_end = max(center_start + 1, normalized.shape[0] - edge_width)
            center = normalized[center_start:center_end]
            edge_rms = float(np.sqrt(np.mean(np.square(edge))))
            center_rms = float(np.sqrt(np.mean(np.square(center)))) if center.size else edge_rms
            edge_ratio = edge_rms / max(center_rms, np.finfo(float).eps)
            edge_artifact_pct = min(100.0, 35.0 * abs(float(np.log2(max(edge_ratio, np.finfo(float).eps)))))

            bow_pct, bow_count, analysed_windows, bow_p95_samples = self._bow_artifact_percentage(normalized)
            migration_artifact_pct = max(bow_pct, edge_artifact_pct)

            velocity_functions = context.get("velocity_functions") or []
            smoothness = velocity_smoothness_metrics(velocity_functions)
            smoothness_available = bool(velocity_functions)

            if migration_artifact_pct > artifact_max_pct:
                findings.append(
                    make_finding(
                        "MIGRATION_ARTIFACTS",
                        QCSeverity.ERROR,
                        f"Estimated migration-artifact coverage is {migration_artifact_pct:.1f}%, exceeding {artifact_max_pct:.1f}%.",
                        category="migration",
                        title="Migration artifacts exceed tolerance",
                        metric_name="migration_artifact_pct",
                        observed_value=migration_artifact_pct,
                        expected_max=artifact_max_pct,
                        unit="%",
                        suggested_action="Review migration aperture, edge taper, anti-alias controls, velocity model, residual moveout and mute design; compare against unmigrated stacks.",
                        context={
                            "bow_artifact_pct": bow_pct,
                            "edge_artifact_pct": edge_artifact_pct,
                            "bow_window_count": bow_count,
                        },
                    )
                )
            elif migration_artifact_pct > artifact_max_pct * 0.6:
                findings.append(
                    make_finding(
                        "MIGRATION_ARTIFACTS_NEAR_LIMIT",
                        QCSeverity.WARNING,
                        f"Estimated migration-artifact coverage is {migration_artifact_pct:.1f}%, close to the {artifact_max_pct:.1f}% limit.",
                        category="migration",
                        title="Migration artifacts near tolerance",
                        metric_name="migration_artifact_pct",
                        observed_value=migration_artifact_pct,
                        expected_max=artifact_max_pct,
                        unit="%",
                        suggested_action="Inspect smiles, bows and edge zones on representative inlines/crosslines before accepting the migrated volume.",
                    )
                )

            if focus_ratio < focus_ratio_min:
                severity = QCSeverity.ERROR if focus_ratio < focus_ratio_min * 0.7 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "MIGRATION_LOW_FOCUS",
                        severity,
                        f"Migration focusing ratio is {focus_ratio:.3f}, below the required {focus_ratio_min:.3f}.",
                        category="migration",
                        title="Insufficient migration focusing",
                        metric_name="migration_focus_ratio",
                        observed_value=focus_ratio,
                        expected_min=focus_ratio_min,
                        unit="ratio",
                        suggested_action="Review the migration velocity field, aperture, anisotropy parameters, residual statics and pre-migration noise attenuation.",
                    )
                )

            if smoothness_available:
                score = smoothness["velocity_smoothness_score_pct"]
                if score < velocity_smoothness_min:
                    findings.append(
                        make_finding(
                            "MIGRATION_VELOCITY_ROUGHNESS",
                            QCSeverity.ERROR,
                            f"Migration-velocity smoothness score is {score:.1f}%, below the required {velocity_smoothness_min:.1f}%.",
                            category="migration",
                            title="Migration velocity model is too rough",
                            metric_name="velocity_smoothness_score_pct",
                            observed_value=score,
                            expected_min=velocity_smoothness_min,
                            unit="%",
                            suggested_action="Apply geologically constrained lateral/vertical smoothing and repick anomalous velocity nodes before rerunning migration.",
                        )
                    )
            else:
                findings.append(
                    make_finding(
                        "MIGRATION_VELOCITY_UNAVAILABLE",
                        QCSeverity.WARNING,
                        "Migration velocity smoothness could not be validated because no velocity functions are available in the processing context.",
                        category="migration",
                        title="Migration velocity model unavailable",
                        suggested_action="Supply the PSTM velocity field or run the velocity-analysis stage on pre-stack gathers.",
                    )
                )

            if edge_ratio > 1.8 or edge_ratio < 0.55:
                findings.append(
                    make_finding(
                        "MIGRATION_EDGE_EFFECT",
                        QCSeverity.WARNING,
                        f"Edge-to-centre RMS ratio is {edge_ratio:.2f}, indicating possible migration aperture or taper effects.",
                        category="migration",
                        title="Migration edge effect detected",
                        metric_name="edge_to_center_rms_ratio",
                        observed_value=edge_ratio,
                        expected_min=0.55,
                        expected_max=1.80,
                        unit="ratio",
                        suggested_action="Increase migration padding/aperture where appropriate and apply a controlled edge taper before delivery.",
                    )
                )

            metrics = {
                "section_trace_count": int(section.shape[0]),
                "section_sample_count": int(section.shape[1]),
                "sample_interval_ms": dt_ms,
                "migration_focus_ratio": focus_ratio,
                "bow_artifact_pct": bow_pct,
                "bow_artifact_window_count": bow_count,
                "analysed_event_window_count": analysed_windows,
                "bow_p95_samples": bow_p95_samples,
                "edge_to_center_rms_ratio": edge_ratio,
                "edge_artifact_pct": edge_artifact_pct,
                "migration_artifact_pct": migration_artifact_pct,
                "velocity_model_available": smoothness_available,
                **smoothness,
                "section_key_first": section_keys[0] if section_keys else None,
                "section_key_last": section_keys[-1] if section_keys else None,
            }
            context["migration_qc"] = {
                "available": True,
                "section": section,
                "dt_ms": dt_ms,
                "section_keys": section_keys,
                "metrics": metrics,
            }
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "MIGRATION_QC_EXCEPTION", exc)
