from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any, Optional

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class StaticsQCStage(QCStage):
    def __init__(self, max_static_magnitude: float = 1000.0, min_static_magnitude: float = 1.0) -> None:
        self.max_static_magnitude = max_static_magnitude
        self.min_static_magnitude = min_static_magnitude

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        headers = context.get("trace_headers")
        if headers is None:
            return QCStageResult(
                stage_name="StaticsQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No trace headers available"})
            )

        try:
            total_static = headers['total_static']
            source_static = headers['source_to_receiver_static']

            total_static_abs = np.abs(total_static)
            source_static_abs = np.abs(source_static)

            total_static_nonzero = total_static_abs[total_static_abs > 0]

            if len(total_static_nonzero) == 0:
                return QCStageResult(
                    stage_name="StaticsQC",
                    status=QCStatus.PASS,
                    summary_json=json.dumps({"message": "No static corrections applied"})
                )

            max_static = float(np.max(total_static_nonzero))
            min_static = float(np.min(total_static_nonzero))
            mean_static = float(np.mean(total_static_nonzero))
            std_static = float(np.std(total_static_nonzero))

            context["static_stats"] = {
                "max": max_static,
                "min": min_static,
                "mean": mean_static,
                "std": std_static,
                "nonzero_count": int(len(total_static_nonzero))
            }

            if max_static > self.max_static_magnitude:
                findings.append(
                    QCFinding(
                        rule_id="statics_high_magnitude",
                        severity=QCSeverity.WARNING,
                        message=f"Maximum static correction {max_static:.1f} ms exceeds {self.max_static_magnitude} ms",
                        suggested_action="Check for extreme near-surface variations"
                    )
                )

            if min_static > 0 and min_static < self.min_static_magnitude:
                pass

            outliers = np.sum((total_static_abs > self.max_static_magnitude) & (total_static_abs > 0))
            if outliers > 0:
                findings.append(
                    QCFinding(
                        rule_id="statics_outliers",
                        severity=QCSeverity.WARNING,
                        message=f"{outliers} static correction outliers detected",
                        suggested_action="Review static correction computation"
                    )
                )

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="StaticsQC",
                status=status,
                summary_json=json.dumps({
                    "max_static_ms": max_static,
                    "min_static_ms": min_static,
                    "mean_static_ms": mean_static,
                    "std_static_ms": std_static,
                    "nonzero_count": int(len(total_static_nonzero)),
                    "outliers": int(outliers)
                }),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="StaticsQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="statics_qc_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Statics QC failed: {str(e)}",
                        suggested_action="Check header data types"
                    )
                ]
            )