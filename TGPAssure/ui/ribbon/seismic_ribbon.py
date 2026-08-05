from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SeismicRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "seismic"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        data_group = RibbonGroup(
            label="Seismic Data",
            actions=[
                RibbonAction("Open SEG-D", "segd_open_file", icon="seg-d"),
                RibbonAction("Open SEG-Y", "segy_open_file", icon="seg-y", accent=True),
                RibbonAction("2D/3D Viewer", "visualization_open", icon="view-3d"),
            ],
        )
        qc_group = RibbonGroup(
            label="Quality Control",
            actions=[
                RibbonAction("SEG-D QC", "segd_run_qc", icon="view-statistics"),
            ],
        )
        display_group = RibbonGroup(
            label="Display",
            actions=[
                RibbonAction("Wiggle", "segd_display_wiggle", icon="office-chart-line"),
                RibbonAction("Variable Density", "segd_display_vd", icon="view-grid"),
                RibbonAction("Color Density", "segd_display_color", icon="view-grid"),
                RibbonAction("Wiggle + Color", "segd_display_wiggle_color", icon="office-chart-line"),
                RibbonAction("Variable Area", "segd_display_va", icon="view-grid"),
                RibbonAction("Fit", "segd_zoom_fit", icon="zoom-fit-best"),
            ],
        )
        return [data_group, qc_group, display_group]
