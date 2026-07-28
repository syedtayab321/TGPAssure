from __future__ import annotations

import json
from typing import Dict, Any, List
from collections import defaultdict

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class SummaryStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        stage_results: List[QCStageResult] = context.get("stage_results", [])
        all_findings: List[QCFinding] = []

        severity_counts = defaultdict(int)
        stage_status_counts = defaultdict(int)

        for result in stage_results:
            stage_status_counts[result.status.value] += 1
            for finding in result.findings:
                all_findings.append(finding)
                severity_counts[finding.severity.value] += 1

        overall_status = QCStatus.PASS
        if severity_counts.get("critical", 0) > 0:
            overall_status = QCStatus.FAIL
        elif severity_counts.get("error", 0) > 0:
            overall_status = QCStatus.FAIL
        elif severity_counts.get("warning", 0) > 0:
            overall_status = QCStatus.WARN

        context["summary"] = {
            "overall_status": overall_status.value,
            "total_stages": len(stage_results),
            "stage_status_counts": dict(stage_status_counts),
            "finding_counts": dict(severity_counts),
            "total_findings": len(all_findings)
        }

        return QCStageResult(
            stage_name="Summary",
            status=overall_status,
            summary_json=json.dumps({
                "overall_status": overall_status.value,
                "total_stages": len(stage_results),
                "stage_status_counts": dict(stage_status_counts),
                "finding_counts": dict(severity_counts),
                "total_findings": len(all_findings)
            }),
            findings=all_findings
        )