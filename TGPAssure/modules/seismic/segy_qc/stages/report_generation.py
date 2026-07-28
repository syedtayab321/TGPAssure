from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any, List

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class ReportGenerationStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        summary_data = context.get("summary", {})
        stage_results: List[QCStageResult] = context.get("stage_results", [])
        file_path = context.get("file_path", "unknown")

        report_payload = {
            "file_path": file_path,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": summary_data.get("overall_status", "unknown"),
            "total_stages": summary_data.get("total_stages", 0),
            "stage_summaries": [],
            "findings_by_severity": {
                "critical": [],
                "error": [],
                "warning": [],
                "info": []
            },
            "statistics": {
                "total_findings": 0,
                "passing_stages": 0,
                "warning_stages": 0,
                "failing_stages": 0,
                "skipped_stages": 0
            }
        }

        severity_map = {
            "critical": QCSeverity.CRITICAL,
            "error": QCSeverity.ERROR,
            "warning": QCSeverity.WARNING,
            "info": QCSeverity.INFO
        }

        for result in stage_results:
            if result.status == QCStatus.PASS:
                report_payload["statistics"]["passing_stages"] += 1
            elif result.status == QCStatus.WARN:
                report_payload["statistics"]["warning_stages"] += 1
            elif result.status == QCStatus.FAIL:
                report_payload["statistics"]["failing_stages"] += 1
            elif result.status == QCStatus.SKIPPED:
                report_payload["statistics"]["skipped_stages"] += 1

            stage_summary = {
                "stage_name": result.stage_name,
                "status": result.status.value,
                "summary": json.loads(result.summary_json) if result.summary_json else {},
                "finding_count": len(result.findings)
            }
            report_payload["stage_summaries"].append(stage_summary)

            for finding in result.findings:
                report_payload["statistics"]["total_findings"] += 1
                severity_key = finding.severity.value
                if severity_key in report_payload["findings_by_severity"]:
                    report_payload["findings_by_severity"][severity_key].append({
                        "rule_id": finding.rule_id,
                        "message": finding.message,
                        "stage": result.stage_name,
                        "location_ref": finding.location_ref,
                        "suggested_action": finding.suggested_action
                    })

        context["report_payload"] = report_payload

        overall_status = QCStatus.PASS
        if report_payload["statistics"]["total_findings"] > 0:
            if len(report_payload["findings_by_severity"]["critical"]) > 0:
                overall_status = QCStatus.FAIL
            elif len(report_payload["findings_by_severity"]["error"]) > 0:
                overall_status = QCStatus.FAIL
            elif len(report_payload["findings_by_severity"]["warning"]) > 0:
                overall_status = QCStatus.WARN

        return QCStageResult(
            stage_name="ReportGeneration",
            status=overall_status,
            summary_json=json.dumps({
                "report_payload": report_payload,
                "report_ready": True
            })
        )