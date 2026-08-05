"""Seismic package with lazy entry points.

The SEG-Y manual viewer, SEG-D viewer, converter and 2D/3D visualization are
kept independent from the removed automated SEG-Y pipeline.
"""
from __future__ import annotations

__all__ = ["SegyReader", "SeismicInterpretationStore"]


def __getattr__(name: str):
    if name == "SegyReader":
        from modules.seismic.segy_reader import SegyReader

        return SegyReader
    if name == "SeismicInterpretationStore":
        from modules.seismic.interpretation_store import SeismicInterpretationStore

        return SeismicInterpretationStore
    raise AttributeError(name)
