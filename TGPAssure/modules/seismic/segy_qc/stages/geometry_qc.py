from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any, Optional

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class GeometryQCStage(QCStage):
    def __init__(self, expected_fold_min: int = 1, expected_fold_max: Optional[int] = None) -> None:
        self.expected_fold_min = expected_fold_min
        self.expected_fold_max = expected_fold_max

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        headers = context.get("trace_headers")
        if headers is None:
            return QCStageResult(
                stage_name="GeometryQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No trace headers available"}),
                findings=[
                    QCFinding(
                        rule_id="geometry_no_headers",
                        severity=QCSeverity.CRITICAL,
                        message="Trace headers not available",
                        suggested_action="Ensure HeaderReading stage completed successfully"
                    )
                ]
            )

        try:
            cdp_values = headers['cdp']

            if len(cdp_values) == 0:
                return QCStageResult(
                    stage_name="GeometryQC",
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": "No CDP values found"}),
                    findings=[
                        QCFinding(
                            rule_id="geometry_no_cdp",
                            severity=QCSeverity.ERROR,
                            message="No CDP values in trace headers",
                            suggested_action="Check that CDP field is populated"
                        )
                    ]
                )

            unique_cdps, counts = np.unique(cdp_values, return_counts=True)
            total_traces = len(cdp_values)
            unique_count = len(unique_cdps)

            fold_stats = {
                "total_traces": total_traces,
                "unique_cdps": unique_count,
                "min_fold": int(np.min(counts)),
                "max_fold": int(np.max(counts)),
                "mean_fold": float(np.mean(counts)),
                "std_fold": float(np.std(counts))
            }

            if self.expected_fold_min is not None:
                below_min = np.sum(counts < self.expected_fold_min)
                if below_min > 0:
                    findings.append(
                        QCFinding(
                            rule_id="geometry_low_fold",
                            severity=QCSeverity.WARNING,
                            message=f"{below_min} CDP bins have fold below {self.expected_fold_min}",
                            suggested_action="Check acquisition geometry or binning parameters"
                        )
                    )

            if self.expected_fold_max is not None:
                above_max = np.sum(counts > self.expected_fold_max)
                if above_max > 0:
                    findings.append(
                        QCFinding(
                            rule_id="geometry_high_fold",
                            severity=QCSeverity.WARNING,
                            message=f"{above_max} CDP bins have fold above {self.expected_fold_max}",
                            suggested_action="Check for excessive redundancy in acquisition"
                        )
                    )

            status = QCStatus.WARN if findings else QCStatus.PASS

            context["fold_stats"] = fold_stats

            return QCStageResult(
                stage_name="GeometryQC",
                status=status,
                summary_json=json.dumps(fold_stats),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="GeometryQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="geometry_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Geometry QC failed: {str(e)}",
                        suggested_action="Check header data types and values"
                    )
                ]
            )