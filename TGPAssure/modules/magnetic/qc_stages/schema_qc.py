from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import BASE_TOTAL_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding


class SchemaQC(MagneticQCStage):
    key = "schema"
    display_name = "Schema and Units"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        findings: list[QCFinding] = []
        if RAW_TOTAL_FIELD not in dataset.channels:
            findings.append(finding("MAG.SCHEMA.TOTAL_FIELD", QCSeverity.CRITICAL, "The rover dataset has no normalized raw total-field channel."))
        if dataset.magnetic_units.lower() not in {"nt", "nanotesla", "nanoteslas"}:
            findings.append(finding("MAG.SCHEMA.FIELD_UNITS", QCSeverity.ERROR, f"Unsupported magnetic-field unit: {dataset.magnetic_units}", suggested_action="Convert total-field measurements to nT before QC."))
        if dataset.role.value == "rover" and not np.any(dataset.valid_coordinate_mask()):
            findings.append(finding("MAG.SCHEMA.COORDINATES", QCSeverity.ERROR, "No valid rover coordinates were imported.", suggested_action="Map easting/northing or longitude/latitude columns."))
        if context.base_dataset is not None and BASE_TOTAL_FIELD not in context.base_dataset.channels:
            findings.append(finding("MAG.SCHEMA.BASE_FIELD", QCSeverity.ERROR, "The base dataset has no normalized base-field channel."))
        duplicate_sources = []
        mapping = dataset.metadata.get("column_mapping", {})
        seen: dict[str, str] = {}
        for canonical, source in mapping.items():
            if source in seen:
                duplicate_sources.append((seen[source], canonical, source))
            else:
                seen[source] = canonical
        if duplicate_sources:
            findings.append(finding("MAG.SCHEMA.DUPLICATE_MAPPING", QCSeverity.WARNING, "One source column is mapped to multiple magnetic fields.", suggested_action="Review the column mapping before final QC.", metadata={"duplicates": duplicate_sources}))
        metrics = {
            "channels": list(dataset.channel_names),
            "magnetic_units": dataset.magnetic_units,
            "coordinate_units": dataset.coordinate_units,
            "crs": dataset.crs,
            "column_mapping": mapping,
            "base_loaded": context.base_dataset is not None,
        }
        return metrics, findings, "Required fields, normalized channels and units checked.", None
