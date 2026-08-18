from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SeismicVisualizationRibbonProvider(RibbonProvider):
    """Clean Petrel-style ribbon for the dedicated 2D/3D geometry viewer."""

    def ribbon_tab_id(self) -> str:
        return "visualization"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        file_group = RibbonGroup(
            label="File",
            actions=[
                RibbonAction("Open", "visualization_open", icon="document-open", accent=True),
                RibbonAction("Save", "visualization_save_session", icon="document-save"),
                RibbonAction("Load", "visualization_load_session", icon="document-open-recent"),
            ],
        )
        window_group = RibbonGroup(
            label="Window",
            actions=[
                RibbonAction("2D", "visualization_inline", icon="view-split-left-right", accent=True),
                RibbonAction("3D", "visualization_show_volume", icon="view-3d"),
                RibbonAction("Map", "visualization_time_slice", icon="map"),
                RibbonAction("Fit", "visualization_fit", icon="zoom-fit-best"),
            ],
        )
        interpretation_group = RibbonGroup(
            label="Interpretation",
            actions=[
                RibbonAction("Horizon", "visualization_pick_horizon", icon="draw-freehand"),
                RibbonAction("Fault", "visualization_pick_fault", icon="draw-line"),
                RibbonAction("Measure", "visualization_measure", icon="measure"),
                RibbonAction("Stop", "visualization_stop_pick", icon="process-stop"),
            ],
        )
        output_group = RibbonGroup(
            label="Output",
            actions=[
                RibbonAction("PNG", "visualization_export_png", icon="image-x-generic", accent=True),
                RibbonAction("KML", "visualization_export_kml", icon="earth"),
                RibbonAction("CSV", "visualization_export_shapefile", icon="text-csv"),
                RibbonAction("HTML", "visualization_export_html", icon="text-html"),
            ],
        )
        return [file_group, window_group, interpretation_group, output_group]
