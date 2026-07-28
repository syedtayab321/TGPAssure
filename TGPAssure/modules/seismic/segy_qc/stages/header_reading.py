from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from typing import Dict, Any

from core.domain.qc_engine import QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding
from modules.seismic.segy_qc.segy_reader import SegyReader


class HeaderReadingStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings = []
        file_path = context.get("file_path")
        if file_path is None:
            return QCStageResult(
                stage_name="HeaderReading",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": "No file path provided"})
            )

        try:
            reader = SegyReader(Path(file_path))
            context["reader"] = reader

            headers = reader.read_trace_headers()
            context["trace_headers"] = headers

            header_fields = [
                'cdp', 'offset', 'source_x', 'source_y',
                'receiver_group_x', 'receiver_group_y',
                'trace_sequence_line', 'trace_sequence_file'
            ]

            header_summary = {}
            for field in header_fields:
                if field in headers.dtype.names:
                    data = headers[field]
                    header_summary[field] = {
                        "min": float(np.min(data)) if len(data) > 0 else 0,
                        "max": float(np.max(data)) if len(data) > 0 else 0,
                        "mean": float(np.mean(data)) if len(data) > 0 else 0,
                        "std": float(np.std(data)) if len(data) > 0 else 0
                    }

            derived_path = context.get("derived_path")
            if derived_path:
                derived_path = Path(derived_path)
                derived_path.mkdir(parents=True, exist_ok=True)
                cache_path = derived_path / f"headers_{context.get('file_uuid', 'unknown')}.npy"
                np.save(cache_path, headers)
                context["header_cache_path"] = str(cache_path)

            return QCStageResult(
                stage_name="HeaderReading",
                status=QCStatus.PASS,
                summary_json=json.dumps({
                    "trace_count": len(headers),
                    "header_fields": list(headers.dtype.names),
                    "header_summary": header_summary
                })
            )

        except Exception as e:
            return QCStageResult(
                stage_name="HeaderReading",
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="header_reading_failed",
                        severity=QCSeverity.ERROR,
                        message=f"Header reading failed: {str(e)}",
                        suggested_action="Check file integrity and format"
                    )
                ]
            )