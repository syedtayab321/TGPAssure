from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any, Optional

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class NavigationQCStage(QCStage):
    def __init__(self, max_velocity: float = 5000.0, min_velocity: float = 100.0) -> None:
        self.max_velocity = max_velocity
        self.min_velocity = min_velocity

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        headers = context.get("trace_headers")
        if headers is None:
            return QCStageResult(
                stage_name="NavigationQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No trace headers available"})
            )

        try:
            source_x = headers['source_x']
            source_y = headers['source_y']

            if len(source_x) < 2:
                return QCStageResult(
                    stage_name="NavigationQC",
                    status=QCStatus.WARN,
                    summary_json=json.dumps({"message": "Less than 2 traces, cannot compute navigation jumps"})
                )

            dx = np.diff(source_x)
            dy = np.diff(source_y)
            distances = np.sqrt(dx**2 + dy**2)

            if len(distances) == 0:
                return QCStageResult(
                    stage_name="NavigationQC",
                    status=QCStatus.PASS,
                    summary_json=json.dumps({"message": "No distances computed"})
                )

            min_distance = float(np.min(distances))
            max_distance = float(np.max(distances))
            mean_distance = float(np.mean(distances))
            std_distance = float(np.std(distances))

            context["distance_stats"] = {
                "min": min_distance,
                "max": max_distance,
                "mean": mean_distance,
                "std": std_distance
            }

            cdp_values = headers['cdp']
            cdp_jumps = np.diff(cdp_values)
            negative_cdp_jumps = np.sum(cdp_jumps < 0)

            if negative_cdp_jumps > 0:
                findings.append(
                    QCFinding(
                        rule_id="navigation_negative_cdp_jump",
                        severity=QCSeverity.WARNING,
                        message=f"{negative_cdp_jumps} negative CDP jumps detected",
                        suggested_action="Check sorting order or acquisition geometry"
                    )
                )

            sample_interval_ms = context.get("sample_interval", 2)
            time_seconds = (len(headers) * sample_interval_ms) / 1000.0

            if time_seconds > 0:
                max_velocity_observed = max_distance / time_seconds if time_seconds > 0 else 0
                context["max_velocity_observed"] = max_velocity_observed

                if max_velocity_observed > self.max_velocity:
                    findings.append(
                        QCFinding(
                            rule_id="navigation_high_velocity",
                            severity=QCSeverity.WARNING,
                            message=f"Maximum velocity {max_velocity_observed:.1f} m/s exceeds threshold {self.max_velocity} m/s",
                            suggested_action="Check coordinate units or time sampling"
                        )
                    )

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="NavigationQC",
                status=status,
                summary_json=json.dumps({
                    "min_distance": min_distance,
                    "max_distance": max_distance,
                    "mean_distance": mean_distance,
                    "negative_cdp_jumps": negative_cdp_jumps,
                    "max_velocity_observed": context.get("max_velocity_observed", 0)
                }),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="NavigationQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="navigation_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Navigation QC failed: {str(e)}",
                        suggested_action="Check header coordinates"
                    )
                ]
            )