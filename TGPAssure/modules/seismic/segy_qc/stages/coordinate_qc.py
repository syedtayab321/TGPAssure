from __future__ import annotations

import json
import numpy as np
from typing import Dict, Any, Optional, Tuple

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class CoordinateQCStage(QCStage):
    def __init__(self, bounding_box: Optional[Tuple[float, float, float, float]] = None) -> None:
        self.bounding_box = bounding_box

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        headers = context.get("trace_headers")
        if headers is None:
            return QCStageResult(
                stage_name="CoordinateQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No trace headers available"})
            )

        try:
            source_x = headers['source_x']
            source_y = headers['source_y']

            if len(source_x) == 0:
                return QCStageResult(
                    stage_name="CoordinateQC",
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": "No coordinates found"})
                )

            min_x = float(np.min(source_x))
            max_x = float(np.max(source_x))
            min_y = float(np.min(source_y))
            max_y = float(np.max(source_y))

            context["coordinate_bounds"] = {
                "min_x": min_x,
                "max_x": max_x,
                "min_y": min_y,
                "max_y": max_y
            }

            if self.bounding_box is not None:
                bb_min_x, bb_max_x, bb_min_y, bb_max_y = self.bounding_box

                outside_x = np.sum((source_x < bb_min_x) | (source_x > bb_max_x))
                outside_y = np.sum((source_y < bb_min_y) | (source_y > bb_max_y))

                if outside_x > 0:
                    findings.append(
                        QCFinding(
                            rule_id="coordinate_outside_x",
                            severity=QCSeverity.ERROR,
                            message=f"{outside_x} traces have X coordinates outside bounding box",
                            suggested_action="Check coordinate system or project area"
                        )
                    )

                if outside_y > 0:
                    findings.append(
                        QCFinding(
                            rule_id="coordinate_outside_y",
                            severity=QCSeverity.ERROR,
                            message=f"{outside_y} traces have Y coordinates outside bounding box",
                            suggested_action="Check coordinate system or project area"
                        )
                    )

                context["outside_coordinates"] = {
                    "outside_x": int(outside_x),
                    "outside_y": int(outside_y)
                }

            coordinate_unit = headers['coordinate_units'][0] if len(headers['coordinate_units']) > 0 else 0
            context["coordinate_units"] = int(coordinate_unit)

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="CoordinateQC",
                status=status,
                summary_json=json.dumps({
                    "min_x": min_x,
                    "max_x": max_x,
                    "min_y": min_y,
                    "max_y": max_y,
                    "coordinate_units": int(coordinate_unit),
                    "outside_x": context.get("outside_coordinates", {}).get("outside_x", 0),
                    "outside_y": context.get("outside_coordinates", {}).get("outside_y", 0)
                }),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="CoordinateQC",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="coordinate_qc_exception",
                        severity=QCSeverity.ERROR,
                        message=f"Coordinate QC failed: {str(e)}",
                        suggested_action="Check header coordinate fields"
                    )
                ]
            )