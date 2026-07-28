"""SEG-Y viewer package with lazy desktop widget loading."""
from __future__ import annotations

__all__ = ["SegyViewerWidget"]


def __getattr__(name: str):
    if name == "SegyViewerWidget":
        from modules.seismic.segy_viewer.segy_viewer_widget import SegyViewerWidget

        return SegyViewerWidget
    raise AttributeError(name)
