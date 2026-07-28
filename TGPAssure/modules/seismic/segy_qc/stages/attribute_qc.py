from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    analytic_attributes,
    circular_phase_spread_deg,
    error_result,
    get_reader_and_index,
    local_coherence,
    make_finding,
    robust_outlier_mask,
    section_from_context,
    stage_result,
    threshold,
)


class AttributeQCStage(QCStage):
    """Compute post-stack instantaneous attributes and coherence anomaly metrics."""

    STAGE_NAME = "AttributeQC"

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            get_reader_and_index(context)
            coherence_min = threshold(context, "coherence_min", 0.35)
            phase_variation_max = threshold(context, "phase_variation_max", 90.0)
            outlier_factor = threshold(context, "attribute_outlier_factor", 6.0)

            migration = context.get("migration_qc") or {}
            section = migration.get("section")
            dt_ms = migration.get("dt_ms")
            section_keys = migration.get("section_keys")
            if section is None or dt_ms is None:
                section, dt_ms, section_keys = section_from_context(context, max_traces=180, max_samples=1800)
            section = np.asarray(section, dtype=np.float64)
            if section.ndim != 2 or section.shape[0] < 2 or section.shape[1] < 16:
                raise ValueError("Attribute QC requires a two-dimensional post-stack section")

            demeaned = section - np.mean(section, axis=1, keepdims=True)
            attributes = analytic_attributes(demeaned, float(dt_ms))
            coherence = local_coherence(demeaned, half_window=2)
            attributes["coherence"] = coherence

            envelope = attributes["envelope"]
            phase = attributes["phase_rad"]
            frequency = attributes["frequency_hz"]
            phase_spread = circular_phase_spread_deg(phase)

            envelope_outliers = robust_outlier_mask(envelope.ravel(), outlier_factor)
            frequency_outliers = robust_outlier_mask(frequency.ravel(), outlier_factor)
            coherence_outliers = coherence.ravel() < coherence_min
            combined_outlier = envelope_outliers | frequency_outliers | coherence_outliers
            combined_outlier_pct = 100.0 * float(np.count_nonzero(combined_outlier)) / max(1, combined_outlier.size)

            finite_coherence = coherence[np.isfinite(coherence)]
            coherence_median = float(np.median(finite_coherence)) if finite_coherence.size else 0.0
            coherence_low_pct = 100.0 * float(np.count_nonzero(finite_coherence < coherence_min)) / max(1, finite_coherence.size)
            phase_p90 = float(np.percentile(phase_spread, 90)) if phase_spread.size else 0.0

            if coherence_median < coherence_min:
                findings.append(
                    make_finding(
                        "ATTRIBUTE_LOW_COHERENCE",
                        QCSeverity.ERROR,
                        f"Median post-stack coherence is {coherence_median:.3f}, below the required {coherence_min:.3f}.",
                        category="attribute",
                        title="Low post-stack coherence",
                        metric_name="coherence_median",
                        observed_value=coherence_median,
                        expected_min=coherence_min,
                        unit="ratio",
                        suggested_action="Review residual statics, migration focusing, random-noise attenuation and structural alignment before interpreting coherence anomalies.",
                    )
                )
            elif coherence_low_pct > 25.0:
                findings.append(
                    make_finding(
                        "ATTRIBUTE_LOCAL_LOW_COHERENCE",
                        QCSeverity.WARNING,
                        f"{coherence_low_pct:.1f}% of attribute samples fall below coherence {coherence_min:.3f}.",
                        category="attribute",
                        title="Localized low-coherence zones",
                        metric_name="low_coherence_pct",
                        observed_value=coherence_low_pct,
                        expected_max=25.0,
                        unit="%",
                        suggested_action="Confirm whether the low-coherence zones represent faults/stratigraphic complexity or processing artifacts.",
                    )
                )

            if phase_p90 > phase_variation_max:
                severity = QCSeverity.ERROR if phase_p90 > phase_variation_max * 1.35 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "ATTRIBUTE_PHASE_VARIATION",
                        severity,
                        f"The 90th-percentile lateral instantaneous-phase spread is {phase_p90:.1f}°, exceeding {phase_variation_max:.1f}°.",
                        category="attribute",
                        title="Excessive instantaneous-phase variation",
                        metric_name="phase_variation_p90_deg",
                        observed_value=phase_p90,
                        expected_max=phase_variation_max,
                        unit="degrees",
                        suggested_action="Check phase consistency, polarity, wavelet stability, residual moveout and migration before using phase-based interpretation.",
                    )
                )

            if combined_outlier_pct > 5.0:
                severity = QCSeverity.ERROR if combined_outlier_pct > 15.0 else QCSeverity.WARNING
                findings.append(
                    make_finding(
                        "ATTRIBUTE_ANOMALIES",
                        severity,
                        f"{combined_outlier_pct:.1f}% of post-stack attribute samples are robust outliers or below the coherence threshold.",
                        category="attribute",
                        title="Attribute anomalies require review",
                        metric_name="attribute_anomaly_pct",
                        observed_value=combined_outlier_pct,
                        expected_max=5.0,
                        unit="%",
                        suggested_action="Cross-check envelope, frequency, phase and coherence anomalies against the seismic section and processing footprint before geological interpretation.",
                        context={
                            "outlier_factor": outlier_factor,
                            "envelope_outlier_count": int(np.count_nonzero(envelope_outliers)),
                            "frequency_outlier_count": int(np.count_nonzero(frequency_outliers)),
                            "low_coherence_count": int(np.count_nonzero(coherence_outliers)),
                        },
                    )
                )

            finite_envelope = envelope[np.isfinite(envelope)]
            finite_frequency = frequency[np.isfinite(frequency)]
            metrics = {
                "section_trace_count": int(section.shape[0]),
                "section_sample_count": int(section.shape[1]),
                "sample_interval_ms": float(dt_ms),
                "envelope_min": float(np.min(finite_envelope)) if finite_envelope.size else 0.0,
                "envelope_max": float(np.max(finite_envelope)) if finite_envelope.size else 0.0,
                "envelope_median": float(np.median(finite_envelope)) if finite_envelope.size else 0.0,
                "instantaneous_frequency_min_hz": float(np.percentile(finite_frequency, 1)) if finite_frequency.size else 0.0,
                "instantaneous_frequency_max_hz": float(np.percentile(finite_frequency, 99)) if finite_frequency.size else 0.0,
                "instantaneous_frequency_median_hz": float(np.median(finite_frequency)) if finite_frequency.size else 0.0,
                "coherence_min": float(np.min(finite_coherence)) if finite_coherence.size else 0.0,
                "coherence_median": coherence_median,
                "low_coherence_pct": coherence_low_pct,
                "phase_variation_median_deg": float(np.median(phase_spread)) if phase_spread.size else 0.0,
                "phase_variation_p90_deg": phase_p90,
                "envelope_outlier_count": int(np.count_nonzero(envelope_outliers)),
                "frequency_outlier_count": int(np.count_nonzero(frequency_outliers)),
                "attribute_anomaly_pct": combined_outlier_pct,
                "section_key_first": section_keys[0] if section_keys else None,
                "section_key_last": section_keys[-1] if section_keys else None,
            }
            context["seismic_attributes"] = {
                "section": section,
                "dt_ms": float(dt_ms),
                "section_keys": section_keys,
                "envelope": envelope,
                "instantaneous_phase_rad": phase,
                "instantaneous_frequency_hz": frequency,
                "coherence": coherence,
                "phase_spread_deg": phase_spread,
                "metrics": metrics,
            }
            context["attribute_qc"] = {"available": True, "metrics": metrics}
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "ATTRIBUTE_QC_EXCEPTION", exc)
