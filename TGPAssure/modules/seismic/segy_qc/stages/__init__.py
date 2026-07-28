"""SEG-Y QC stage namespace.

Stages are loaded lazily so numerical/headless QC components do not import
optional format/UI dependencies unless a specific legacy stage requires them.
"""
from __future__ import annotations

from importlib import import_module

_STAGE_MODULES = {
    "UploadStage": "upload",
    "ValidationStage": "validation",
    "MetadataExtractionStage": "metadata_extraction",
    "HeaderReadingStage": "header_reading",
    "GeometryQCStage": "geometry_qc",
    "NavigationQCStage": "navigation_qc",
    "TraceQCStage": "trace_qc",
    "AmplitudeQCStage": "amplitude_qc",
    "NoiseQCStage": "noise_qc",
    "FrequencyQCStage": "frequency_qc",
    "StaticsQCStage": "statics_qc",
    "CoordinateQCStage": "coordinate_qc",
    "ResidualStaticsQCStage": "residual_statics_qc",
    "VelocityQCStage": "velocity_qc",
    "NMOQCStage": "nmo_qc",
    "StackQCStage": "stack_qc",
    "MigrationQCStage": "migration_qc",
    "AttributeQCStage": "attribute_qc",
    "RepeatabilityQCStage": "repeatability_qc",
    "SummaryStage": "summary",
    "ReportGenerationStage": "report_generation",
}

__all__ = list(_STAGE_MODULES)


def __getattr__(name: str):
    module_name = _STAGE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    module = import_module(f"modules.seismic.segy_qc.stages.{module_name}")
    return getattr(module, name)
