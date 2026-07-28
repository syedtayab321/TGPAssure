from __future__ import annotations

from pathlib import Path
from typing import Any

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding


class FileIntegrityQC(MagneticQCStage):
    key = "file_integrity"
    display_name = "File Integrity"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        findings: list[QCFinding] = []
        dataset = context.rover_dataset
        source = Path(dataset.source_path)
        exists = source.exists()
        readable = source.is_file() and source.stat().st_size > 0 if exists else False
        if not exists:
            findings.append(finding("MAG.FILE.MISSING", QCSeverity.ERROR, "The magnetic source file no longer exists.", suggested_action="Restore or re-import the original magnetic file."))
        elif not readable:
            findings.append(finding("MAG.FILE.EMPTY", QCSeverity.ERROR, "The magnetic source file is empty or unreadable."))

        rejected = int(dataset.metadata.get("rejected_rows", 0) or 0)
        malformed_sensor = int(dataset.metadata.get("malformed_sensor_records", 0) or 0)
        malformed_gps = int(dataset.metadata.get("malformed_gps_records", 0) or 0)
        malformed_total = rejected + malformed_sensor + malformed_gps
        source_sensor = int(dataset.metadata.get("source_sensor_records", dataset.record_count) or dataset.record_count)
        malformed_pct = 100.0 * malformed_total / max(source_sensor, 1)
        if malformed_total:
            severity = QCSeverity.WARNING if malformed_pct <= 1.0 else QCSeverity.ERROR
            findings.append(
                finding(
                    "MAG.FILE.MALFORMED_RECORDS",
                    severity,
                    f"{malformed_total} source records could not be normalized ({malformed_pct:.3f}%).",
                    suggested_action="Inspect malformed/truncated sensor or GPS records before final acceptance.",
                    metadata={
                        "rejected_rows": rejected,
                        "malformed_sensor_records": malformed_sensor,
                        "malformed_gps_records": malformed_gps,
                    },
                )
            )

        georef_inferred = dataset.quality_flags.get("georef_edge_inferred")
        georef_inferred_count = int(georef_inferred.sum()) if georef_inferred is not None else 0
        if georef_inferred_count:
            findings.append(
                finding(
                    "MAG.FILE.INFERRED_GEOREF_EDGE",
                    QCSeverity.INFO,
                    f"{georef_inferred_count} edge sensor records use inferred GPS timing/position because the sensor stream begins before or ends after an adjacent GPS fix.",
                    suggested_action="This is expected for event-ordered logs without sensor timestamps; keep the inference documented in processing provenance.",
                )
            )

        metrics = {
            "source_exists": exists,
            "source_readable": readable,
            "file_size_bytes": source.stat().st_size if readable else 0,
            "record_count": dataset.record_count,
            "checksum": dataset.checksum,
            "reader": dataset.metadata.get("reader"),
            "format_id": dataset.metadata.get("format_id"),
            "source_sensor_records": dataset.metadata.get("source_sensor_records"),
            "source_gps_records": dataset.metadata.get("source_gps_records"),
            "rejected_rows": rejected,
            "malformed_sensor_records": malformed_sensor,
            "malformed_gps_records": malformed_gps,
            "malformed_record_pct": malformed_pct,
            "edge_georeference_inference_count": georef_inferred_count,
        }
        return metrics, findings, "Source file, native-record parsing and imported record integrity checked.", None
