from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class AmplitudeQCStage(QCStage):
    def __init__(self, dc_bias_threshold: float = 0.1) -> None:
        self.dc_bias_threshold = dc_bias_threshold

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        reader = context.get("reader")
        if reader is None:
            return QCStageResult(
                stage_name="AmplitudeQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No SEG-Y reader available"})
            )

        try:
            trace_count = reader.get_trace_count()
            sample_count = reader.get_sample_count()

            if trace_count == 0:
                return QCStageResult(
                    stage_name="AmplitudeQC",
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": "No traces to analyze"})
                )

            chunk_size = min(50, trace_count)
            all_means = []
            all_vars = []
            all_rms = []

            for i in range(0, trace_count, chunk_size):
                end = min(i + chunk_size, trace_count)
                data = reader.read_trace_window((i, end), (0, sample_count))

                for j in range(data.shape[0]):
                    trace_data = data[j, :]
                    all_means.append(float(np.mean(trace_data)))
                    all_vars.append(float(np.var(trace_data)))
                    all_rms.append(float(np.sqrt(np.mean(np.square(trace_data, dtype=np.float64)))))

            mean_amplitude = float(np.mean(all_means))
            var_amplitude = float(np.mean(all_vars))
            std_amplitude = float(np.std(all_means))
            mean_rms = float(np.mean(all_rms)) if all_rms else 0.0
            rms_variation = (float(np.std(all_rms)) / mean_rms) if mean_rms > 1e-12 else 0.0

            context["amplitude_stats"] = {
                "mean": mean_amplitude,
                "variance": var_amplitude,
                "std": std_amplitude,
                "mean_rms": mean_rms,
                "rms_cv": rms_variation
            }

            if abs(mean_amplitude) > self.dc_bias_threshold:
                findings.append(
                    QCFinding(
                        rule_id="amplitude_dc_bias",
                        severity=QCSeverity.WARNING,
                        message=f"DC bias detected: mean amplitude = {mean_amplitude:.4f}",
                        suggested_action="Check for DC offset in recording system"
                    )
                )

            # Trace-to-trace RMS coefficient of variation is stable around zero-mean
            # seismic data; dividing the standard deviation of trace means by a
            # near-zero global mean produced false warnings on healthy data.
            amplitude_variation = rms_variation
            if amplitude_variation > 1.0:
                findings.append(
                    QCFinding(
                        rule_id="amplitude_high_variation",
                        severity=QCSeverity.WARNING,
                        message=f"High trace RMS variation detected: CV = {amplitude_variation:.2f}",
                        suggested_action="Check for gain inconsistencies, acquisition coupling, or anomalous traces"
                    )
                )

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="AmplitudeQC",
                status=status,
                summary_json=json.dumps({
                    "mean_amplitude": mean_amplitude,
                    "variance": var_amplitude,
                    "std_amplitude": std_amplitude,
                    "amplitude_variation": amplitude_variation
                }),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="AmplitudeQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="amplitude_qc_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Amplitude QC failed: {str(e)}",
                        suggested_action="Check data format and memory"
                    )
                ]
            )