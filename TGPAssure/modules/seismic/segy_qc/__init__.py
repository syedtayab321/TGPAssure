"""SEG-Y QC package with lazy GUI/controller imports.

This keeps the standards-aware reader available to command-line validation,
automated tests, and server-side QC without requiring the PySide6 desktop stack.
"""
from __future__ import annotations

__all__ = [
    "SegyReader",
    "SegyTextHeader",
    "SegyBinaryHeader",
    "SegyTraceHeader",
    "SegyQcPipeline",
    "SegyQcController",
    "SegyQcView",
]


def __getattr__(name: str):
    if name in {"SegyReader", "SegyTextHeader", "SegyBinaryHeader", "SegyTraceHeader"}:
        from modules.seismic.segy_qc import segy_reader

        return getattr(segy_reader, name)
    if name == "SegyQcPipeline":
        from modules.seismic.segy_qc.segy_qc_pipeline import SegyQcPipeline

        return SegyQcPipeline
    if name == "SegyQcController":
        from modules.seismic.segy_qc.segy_qc_controller import SegyQcController

        return SegyQcController
    if name == "SegyQcView":
        from modules.seismic.segy_qc.segy_qc_view import SegyQcView

        return SegyQcView
    raise AttributeError(name)
