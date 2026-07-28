from __future__ import annotations
from typing import List
from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider

class SegyViewerRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "segy_viewer"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("File", [
                RibbonAction("Open SEG-Y", "segy_open_file", icon="seg-y", accent=True),
                RibbonAction("Open 2D/3D", "segy_open_2d3d", icon="view-3d"),
                RibbonAction("Export Image", "segy_viewer_export_image", icon="document-save"),
            ]),
            RibbonGroup("Display", [
                RibbonAction("Wiggle", "segy_viewer_wiggle", icon="office-chart-line"),
                RibbonAction("Variable Area", "segy_viewer_va", icon="view-grid"),
                RibbonAction("Variable Density", "segy_viewer_vd", icon="view-grid"),
                RibbonAction("Color Density", "segy_viewer_color", icon="view-grid"),
                RibbonAction("Fit", "segy_viewer_fit", icon="zoom-fit-best"),
            ]),
            RibbonGroup("Analysis", [
                RibbonAction("Headers", "segy_viewer_headers", icon="document-properties"),
                RibbonAction("Trace Analysis", "segy_viewer_trace_analysis", icon="view-statistics"),
                RibbonAction("Run SEG-Y QC", "segy_run_qc", icon="media-playback-start", accent=True),
            ]),
        ]
