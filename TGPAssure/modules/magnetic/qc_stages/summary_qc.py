from __future__ import annotations

from collections import Counter
from typing import Any

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, score_from_outcomes


class SummaryQC(MagneticQCStage):
    key = "summary"
    display_name = "Final Magnetic Summary"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        prior = list(context.stage_outcomes.values())
        statuses = [stage.status for stage in prior]
        score = score_from_outcomes(statuses)
        counts = Counter(status.value for status in statuses)
        critical_count = sum(1 for stage in prior for item in stage.findings if item.severity == QCSeverity.CRITICAL)
        error_count = sum(1 for stage in prior for item in stage.findings if item.severity == QCSeverity.ERROR)
        warning_count = sum(1 for stage in prior for item in stage.findings if item.severity == QCSeverity.WARNING)
        if critical_count or error_count:
            final_status = QCStatus.FAIL
        elif warning_count:
            final_status = QCStatus.WARN
        else:
            final_status = QCStatus.PASS
        findings: list[QCFinding] = []
        if final_status == QCStatus.FAIL:
            findings.append(finding("MAG.SUMMARY.NOT_ACCEPTED", QCSeverity.ERROR, "Magnetic data are not ready for final acceptance because one or more error-level findings remain.", suggested_action="Resolve critical/error findings and rerun the relevant stages."))
        elif final_status == QCStatus.WARN:
            findings.append(finding("MAG.SUMMARY.CONDITIONAL", QCSeverity.WARNING, "Magnetic data pass with review items that should be documented before delivery."))
        timestamp_outcome = context.stage_outcomes.get("timestamp")
        invalid_timestamp_pct = float(timestamp_outcome.metrics.get("invalid_timestamp_pct", 0.0)) if timestamp_outcome else 0.0
        metrics = {
            "overall_score": score,
            "stage_status_counts": dict(counts),
            "critical_findings": critical_count,
            "error_findings": error_count,
            "warning_findings": warning_count,
            "data_completeness_pct": round(max(0.0, 100.0 - invalid_timestamp_pct), 2),
            "processing_ready": not any(stage.status == QCStatus.FAIL for stage in prior if stage.stage_key in {"file_integrity", "schema", "timestamp", "coordinate", "sensor", "base_station"}),
            "mapping_ready": not any(stage.status == QCStatus.FAIL for stage in prior if stage.stage_key in {"coordinate", "boundary", "line_geometry", "leveling", "grid"}),
        }
        return metrics, findings, f"Magnetic QC completed with {final_status.value.upper()} status and score {score:.1f}.", final_status
