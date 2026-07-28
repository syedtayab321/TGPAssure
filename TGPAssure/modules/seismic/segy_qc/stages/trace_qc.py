from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any, Optional

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class TraceQCStage(QCStage):
    def __init__(self, noise_floor_threshold: float = 1e-6) -> None:
        self.noise_floor_threshold = noise_floor_threshold

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        reader = context.get("reader")
        if reader is None:
            return QCStageResult(
                stage_name="TraceQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No SEG-Y reader available"})
            )

        try:
            trace_count = reader.get_trace_count()
            sample_count = reader.get_sample_count()

            if trace_count == 0:
                return QCStageResult(
                    stage_name="TraceQC",
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": "No traces to analyze"})
                )

            chunk_size = min(100, trace_count)
            rms_values = np.zeros(trace_count)
            dead_traces = []

            for i in range(0, trace_count, chunk_size):
                end = min(i + chunk_size, trace_count)
                data = reader.read_trace_window((i, end), (0, sample_count))

                for j in range(data.shape[0]):
                    trace_data = data[j, :]
                    rms = np.sqrt(np.mean(trace_data**2))
                    rms_values[i + j] = rms

                    if rms < self.noise_floor_threshold:
                        dead_traces.append(i + j)

            context["rms_values"] = rms_values
            context["dead_traces"] = dead_traces

            rms_stats = {
                "min": float(np.min(rms_values)),
                "max": float(np.max(rms_values)),
                "mean": float(np.mean(rms_values)),
                "std": float(np.std(rms_values))
            }

            dead_percentage = (len(dead_traces) / trace_count) * 100 if trace_count > 0 else 0

            if len(dead_traces) > 0:
                findings.append(
                    QCFinding(
                        rule_id="trace_dead_traces",
                        severity=QCSeverity.WARNING if dead_percentage < 10 else QCSeverity.ERROR,
                        message=f"{len(dead_traces)} dead traces detected ({dead_percentage:.1f}%)",
                        suggested_action="Check gain settings and recording equipment" if dead_percentage < 10 else "Investigate significant data loss"
                    )
                )

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="TraceQC",
                status=status,
                summary_json=json.dumps({
                    "trace_count": trace_count,
                    "rms_stats": rms_stats,
                    "dead_trace_count": len(dead_traces),
                    "dead_trace_percentage": dead_percentage
                }),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="TraceQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="trace_qc_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Trace QC failed: {str(e)}",
                        suggested_action="Check data integrity and memory"
                    )
                ]
            )