from __future__ import annotations

from modules.seismic.visualization.models import (
    GainSettings,
    InterpretationObject,
    InterpretationPoint,
    QcTraceFlag,
    SectionData,
    SectionRequest,
    VisualizationSession,
    VolumeData,
    WellPath,
)

__all__ = [
    "SeismicVisualizationDashboard",
    "UnifiedSeismicDataSource",
    "GainSettings",
    "InterpretationObject",
    "InterpretationPoint",
    "QcTraceFlag",
    "SectionData",
    "SectionRequest",
    "VisualizationSession",
    "VolumeData",
    "WellPath",
]


def __getattr__(name: str):
    if name == "SeismicVisualizationDashboard":
        from modules.seismic.visualization.dashboard import SeismicVisualizationDashboard

        return SeismicVisualizationDashboard
    if name == "UnifiedSeismicDataSource":
        from modules.seismic.visualization.data_source import UnifiedSeismicDataSource

        return UnifiedSeismicDataSource
    raise AttributeError(name)
