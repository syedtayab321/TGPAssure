from __future__ import annotations

from typing import Any

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding


class MetadataQC(MagneticQCStage):
    key = "metadata"
    display_name = "Survey Metadata"

    REQUIRED_FINAL = ("instrument_make", "instrument_model", "sensor_serial_number", "operator", "project_name")

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        metadata = context.rover_dataset.metadata
        findings: list[QCFinding] = []
        missing = [key for key in self.REQUIRED_FINAL if not str(metadata.get(key, "")).strip()]
        if missing:
            severity = QCSeverity.WARNING if context.profile_name in {"field", "standard"} else QCSeverity.ERROR
            findings.append(finding("MAG.META.MISSING", severity, f"Required survey metadata is incomplete: {', '.join(missing)}.", suggested_action="Complete instrument, operator and project metadata before delivery.", metadata={"missing": missing}))
        if not context.rover_dataset.crs:
            findings.append(finding("MAG.META.CRS", QCSeverity.WARNING, "The rover coordinate reference system is not defined.", suggested_action="Assign the verified project CRS before map, boundary or grid QC."))
        metrics = {
            "survey_type": context.rover_dataset.survey_type.value,
            "role": context.rover_dataset.role.value,
            "metadata_completeness_pct": round(100.0 * (len(self.REQUIRED_FINAL) - len(missing)) / len(self.REQUIRED_FINAL), 2),
            "missing_fields": missing,
            "instrument_make": metadata.get("instrument_make"),
            "instrument_model": metadata.get("instrument_model"),
            "sensor_serial_number": metadata.get("sensor_serial_number"),
        }
        return metrics, findings, "Survey and instrument metadata reviewed.", None
