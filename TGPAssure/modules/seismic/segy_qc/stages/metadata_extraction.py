from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

import ebcdic

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding


class MetadataExtractionStage(QCStage):
    def __init__(self, client_pattern: str = r"CLIENT\s*[:=]\s*([^\n]+)", 
                 survey_pattern: str = r"SURVEY\s*[:=]\s*([^\n]+)") -> None:
        self.client_pattern = client_pattern
        self.survey_pattern = survey_pattern

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        file_path = context.get("file_path")
        if file_path is None:
            return QCStageResult(
                stage_name="MetadataExtraction",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No file path provided"})
            )

        path = Path(file_path)
        if not path.exists():
            return QCStageResult(
                stage_name="MetadataExtraction",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": f"File not found: {file_path}"})
            )

        try:
            with open(path, "rb") as f:
                ebcdic_bytes = f.read(3200)

            ebcdic_decoder = ebcdic.EBCDIC()
            decoded_text = ebcdic_decoder.decode(ebcdic_bytes)

            lines = [decoded_text[i:i+80] for i in range(0, 3200, 80)]
            context["ebcdic_lines"] = lines

            client = self._extract_field(decoded_text, self.client_pattern)
            if client:
                context["client"] = client
            else:
                findings.append(
                    QCFinding(
                        rule_id="metadata_no_client",
                        severity=QCSeverity.WARNING,
                        message="Client name not found in textual header",
                        suggested_action="Add CLIENT field to textual header"
                    )
                )

            survey = self._extract_field(decoded_text, self.survey_pattern)
            if survey:
                context["survey_name"] = survey
            else:
                findings.append(
                    QCFinding(
                        rule_id="metadata_no_survey",
                        severity=QCSeverity.WARNING,
                        message="Survey name not found in textual header",
                        suggested_action="Add SURVEY field to textual header"
                    )
                )

            context["textual_header"] = decoded_text

            metadata = {
                "client": client,
                "survey": survey,
                "line_count": len(lines),
                "header_preview": "\n".join(lines[:5])
            }

            status = QCStatus.WARN if findings else QCStatus.PASS

            return QCStageResult(
                stage_name="MetadataExtraction",
                status=status,
                summary_json=json.dumps(metadata),
                findings=findings
            )

        except Exception as e:
            return QCStageResult(
                stage_name="MetadataExtraction",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="metadata_extraction_failed",
                        severity=QCSeverity.ERROR,
                        message=f"Metadata extraction failed: {str(e)}",
                        suggested_action="Check file encoding and format"
                    )
                ]
            )

    def _extract_field(self, text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None