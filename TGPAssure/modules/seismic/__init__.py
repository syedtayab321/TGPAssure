"""Seismic package with lazy entry points.

Core SEG-Y/SEG-D readers and numerical utilities must remain importable in
headless QC/batch environments where Qt/OpenGL are intentionally unavailable.
GUI and controller dependencies are therefore loaded only when requested.
"""
from __future__ import annotations

__all__ = ["SegyQcController", "SeismicInterpretationStore"]


def __getattr__(name: str):
    if name == "SegyQcController":
        from modules.seismic.segy_qc.segy_qc_controller import SegyQcController

        return SegyQcController
    if name == "SeismicInterpretationStore":
        from modules.seismic.interpretation_store import SeismicInterpretationStore

        return SeismicInterpretationStore
    raise AttributeError(name)
