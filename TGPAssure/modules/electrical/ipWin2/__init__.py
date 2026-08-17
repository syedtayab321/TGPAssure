"""Standalone IPWin2-style VES/IP 1D electrical submodule.

This package is intentionally separate from the Prosys II electrical/IP QC
workspace. It owns the IPWin2-style point table, model table, apparent
resistivity curve, pseudo-section and resistivity-section views and is opened
as its own TGPAssure document tab.
"""

from .dashboard import (
    IpWin2Dashboard,
    Ipi2WinDashboard,
    ModelLayer,
    OptionsDialog,
    SimpleChoiceDialog,
    VesPointDialog,
    VesRow,
)

__all__ = [
    "IpWin2Dashboard",
    "Ipi2WinDashboard",
    "VesRow",
    "ModelLayer",
    "VesPointDialog",
    "OptionsDialog",
    "SimpleChoiceDialog",
]
