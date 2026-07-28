from __future__ import annotations

from typing import Any

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import (
    DESPIKED_TOTAL_FIELD,
    DIURNAL_CORRECTED_FIELD,
    DIURNAL_CORRECTION,
    IGRF_TOTAL_FIELD,
    LEVELED_FIELD,
    MICROLEVELED_FIELD,
    RAW_TOTAL_FIELD,
    RESIDUAL_FIELD,
    VERTICAL_GRADIENT,
)
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding


class CorrectionAuditQC(MagneticQCStage):
    key = "correction_audit"
    display_name = "Processing Audit"

    DERIVED_CHANNELS = {
        DESPIKED_TOTAL_FIELD,
        DIURNAL_CORRECTION,
        DIURNAL_CORRECTED_FIELD,
        IGRF_TOTAL_FIELD,
        RESIDUAL_FIELD,
        LEVELED_FIELD,
        MICROLEVELED_FIELD,
        VERTICAL_GRADIENT,
    }

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        findings: list[QCFinding] = []
        if RAW_TOTAL_FIELD not in dataset.channels:
            findings.append(finding("MAG.AUDIT.RAW_MISSING", QCSeverity.CRITICAL, "The immutable raw total-field channel is missing."))

        provenance = [entry.as_dict() for entry in dataset.provenance]
        seen_channels: set[str] = set()
        duplicate_operations: list[str] = []
        for entry in dataset.provenance:
            if entry.channel in seen_channels:
                duplicate_operations.append(entry.channel)
            seen_channels.add(entry.channel)
            external_parent = entry.operation in {"base_interpolation", "external_igrf_model"}
            if entry.parent_channel and "," not in entry.parent_channel and entry.parent_channel not in dataset.channels and not external_parent:
                findings.append(finding("MAG.AUDIT.PARENT", QCSeverity.ERROR, f"Derived channel {entry.channel} refers to unavailable parent {entry.parent_channel}."))
        if duplicate_operations:
            findings.append(
                finding(
                    "MAG.AUDIT.DUPLICATE",
                    QCSeverity.WARNING,
                    "One or more output channel names appear multiple times in processing history.",
                    metadata={"channels": duplicate_operations},
                )
            )

        derived_present = sorted(self.DERIVED_CHANNELS.intersection(dataset.channels) - {RAW_TOTAL_FIELD})
        missing_provenance = [name for name in derived_present if name not in seen_channels]
        if missing_provenance:
            findings.append(
                finding(
                    "MAG.AUDIT.PROVENANCE",
                    QCSeverity.ERROR,
                    "One or more processed/derived magnetic channels exist without processing provenance.",
                    suggested_action="Recreate derived products through the traceable processing engine.",
                    metadata={"channels": missing_provenance},
                )
            )

        # Native auxiliary channels (GPS HDOP, satellites, BNO components,
        # sensor counters, etc.) come directly from the acquisition file and
        # are not processing products, so they correctly require no provenance.
        acquisition_channels = sorted(set(dataset.channels) - self.DERIVED_CHANNELS)
        return {
            "raw_channel_preserved": RAW_TOTAL_FIELD in dataset.channels,
            "channel_count": len(dataset.channels),
            "acquisition_auxiliary_channels": acquisition_channels,
            "derived_channels": derived_present,
            "processing_step_count": len(provenance),
            "provenance": provenance,
        }, findings, "Raw-data preservation, native acquisition channels and processing lineage checked.", None
