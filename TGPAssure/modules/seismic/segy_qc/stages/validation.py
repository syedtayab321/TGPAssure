from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult, QCStatus
from modules.seismic.segy_qc.segy_reader import SegyReader, UnsupportedSampleFormatError


class ValidationStage(QCStage):
    """Standards-aware SEG-Y structural validation.

    Earlier versions incorrectly read sample format/counts from bytes 1-8 of the
    binary header. The stage now delegates header semantics and byte order to the
    authoritative SegyReader and validates actual trace boundaries.
    """

    MIN_HEADER_SIZE = 3600

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        file_path = context.get("file_path")
        if not file_path:
            return self._failure("validation_no_file", "No file path provided", "Ensure file_path is set in context")
        path = Path(file_path).expanduser()
        if not path.is_file():
            return self._failure("validation_file_missing", f"File not found: {path}", "Select a readable SEG-Y file")
        file_size = path.stat().st_size
        if file_size < self.MIN_HEADER_SIZE:
            return self._failure("validation_too_small", f"File size {file_size} bytes is less than the mandatory 3600-byte SEG-Y header", "Verify the source file")

        findings: list[QCFinding] = []
        try:
            reader = SegyReader(path)
            index = reader.scan_trace_headers()
            binary = reader.binary_header
            trace_count = index.trace_count
            sample_count = int(binary.samples_per_trace)
            sample_interval_us = int(binary.sample_interval_us)

            if trace_count <= 0:
                findings.append(QCFinding("validation_no_traces", QCSeverity.ERROR, "No complete SEG-Y traces were indexed", suggested_action="Check trace headers, sample format and file truncation"))
            if sample_count <= 0 and trace_count:
                findings.append(QCFinding("validation_invalid_sample_count", QCSeverity.ERROR, "Binary header does not provide a valid samples-per-trace value", suggested_action="Review variable-length trace headers"))
            if sample_interval_us <= 0:
                findings.append(QCFinding("validation_invalid_sample_interval", QCSeverity.WARNING, "Binary header sample interval is zero; per-trace intervals will be used where available", suggested_action="Verify acquisition/processing metadata"))
            if index.truncated:
                findings.append(QCFinding("validation_truncated_trace", QCSeverity.ERROR, "The final trace payload is truncated or inconsistent with its header", suggested_action="Recover/re-export the SEG-Y file before processing"))
            if index.trailing_bytes:
                findings.append(QCFinding("validation_trailing_bytes", QCSeverity.WARNING, f"{index.trailing_bytes:,} trailing byte(s) remain after the final complete trace", suggested_action="Verify vendor extensions or file integrity"))
            if getattr(reader, "_legacy_compact_header", False):
                findings.append(QCFinding("validation_legacy_header", QCSeverity.INFO, "Detected legacy compact TGPAssure header compatibility mode rather than a standards-compliant SEG-Y binary header", suggested_action="Re-export as standard SEG-Y for interchange"))

            if any(item.severity in {QCSeverity.ERROR, QCSeverity.CRITICAL} for item in findings):
                status = QCStatus.FAIL
            elif any(item.severity == QCSeverity.WARNING for item in findings):
                status = QCStatus.WARN
            else:
                status = QCStatus.PASS

            context.update({
                "validated": status != QCStatus.FAIL,
                "reader": reader,
                "format_code": int(binary.sample_format_code),
                "trace_count": trace_count,
                "sample_count": sample_count,
                "sample_interval": sample_interval_us / 1000.0,
                "trace_index": index,
            })
            return QCStageResult(
                stage_name="Validation",
                status=status,
                summary_json=json.dumps({
                    "file_size": file_size,
                    "format_code": int(binary.sample_format_code),
                    "sample_format": reader.sample_format_name,
                    "byte_order": "big" if binary.endian == ">" else "little",
                    "revision": binary.revision,
                    "trace_count": trace_count,
                    "sample_count": sample_count,
                    "sample_interval_ms": sample_interval_us / 1000.0,
                    "extended_text_headers": int(reader.extended_header_count),
                    "trailing_bytes": int(index.trailing_bytes),
                    "truncated": bool(index.truncated),
                }),
                findings=findings,
            )
        except UnsupportedSampleFormatError as exc:
            return self._failure(
                "validation_invalid_format_code",
                f"Unsupported SEG-Y sample format code: {exc.format_code}",
                "Re-export the file using a supported SEG-Y sample format",
            )
        except Exception as exc:
            return self._failure("validation_exception", f"SEG-Y validation failed: {exc}", "Check file format, permissions and binary/trace headers")

    @staticmethod
    def _failure(rule_id: str, message: str, action: str) -> QCStageResult:
        return QCStageResult(
            stage_name="Validation",
            status=QCStatus.FAIL,
            summary_json=json.dumps({"error": message}),
            findings=[QCFinding(rule_id=rule_id, severity=QCSeverity.CRITICAL, message=message, suggested_action=action)],
        )
