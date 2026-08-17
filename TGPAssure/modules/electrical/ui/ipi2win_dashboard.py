"""Compatibility wrapper for the standalone IPWin2 electrical submodule.

New code should import from ``modules.electrical.ipWin2.dashboard``.  This
wrapper is kept so older TGPAssure integrations that still import
``modules.electrical.ui.ipi2win_dashboard`` do not break.
"""

from modules.electrical.ipWin2.dashboard import (  # noqa: F401
    IpWin2Dashboard,
    Ipi2WinDashboard,
    ModelLayer,
    OptionsDialog,
    SimpleChoiceDialog,
    VesPointDialog,
    VesRow,
)
