from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SegdRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "segd"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        file_group = RibbonGroup(
            label="SEG-D File",
            actions=[
                RibbonAction("Open SEG-D", "segd_open_file", icon="document-open", accent=True),
                RibbonAction("Open 2D/3D", "segd_open_2d3d", icon="view-3d"),
                RibbonAction("Reload", "segd_reload", icon="view-refresh"),
                RibbonAction("Export Image", "segd_export_image", icon="document-export"),
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
        gain_group = RibbonGroup(
            label="Gain",
            actions=[
                RibbonAction("No Gain", "segd_gain_none", icon="audio-volume-muted"),
                RibbonAction("AGC", "segd_gain_agc", icon="audio-volume-high"),
                RibbonAction("Trace Balance", "segd_gain_trace_balance", icon="transform-scale"),
                RibbonAction("Fixed Gain", "segd_gain_fixed", icon="audio-volume-medium"),
            ],
        )
        tools_group = RibbonGroup(
            label="Tools",
            actions=[
                RibbonAction("Pan", "segd_pan", icon="transform-move"),
                RibbonAction("Pick", "segd_pick", icon="draw-freehand"),
                RibbonAction("Measure", "segd_measure", icon="measure"),
            ],
        )
        qc_group = RibbonGroup(
            label="QC",
            actions=[
                RibbonAction("Run QC", "segd_run_qc", icon="media-playback-start"),
                RibbonAction("Header QC", "segd_header_qc", icon="dialog-information"),
                RibbonAction("Trace QC", "segd_trace_qc", icon="view-statistics"),
            ],
        )
        return [file_group, display_group, gain_group, tools_group, qc_group]