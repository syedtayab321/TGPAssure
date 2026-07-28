from __future__ import annotations

from typing import List
from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class VibroseisRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "vibroseis"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("Workspace", [
                RibbonAction("Open Vibroseis", "vibroseis_open", icon="media-playback-start", accent=True),
                RibbonAction("Load Telemetry", "vibroseis_load", icon="document-open"),
            ]),
            RibbonGroup("Source Design", [
                RibbonAction("Sweep Designer", "vibroseis_sweep", icon="view-statistics", accent=True),
                RibbonAction("Generate Sweep", "vibroseis_generate", icon="media-playback-start"),
                RibbonAction("Export Pilot", "vibroseis_export_pilot", icon="document-save"),
            ]),
            RibbonGroup("Source QC", [
                RibbonAction("Signal QC", "vibroseis_signal_qc", icon="dialog-ok-apply"),
                RibbonAction("Correlation", "vibroseis_correlation", icon="view-statistics"),
                RibbonAction("Ground Force", "vibroseis_ground_force", icon="view-statistics"),
            ]),
            RibbonGroup("Planning", [
                RibbonAction("Productivity", "vibroseis_productivity", icon="view-statistics"),
            ]),
        ]
