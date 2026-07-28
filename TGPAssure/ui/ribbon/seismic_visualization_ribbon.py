from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SeismicVisualizationRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "visualization"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        file_group = RibbonGroup(
            label="File",
            actions=[
                RibbonAction("Open", "visualization_open", icon="document-open", accent=True),
                RibbonAction("Save Session", "visualization_save_session", icon="document-save"),
                RibbonAction("Load Session", "visualization_load_session", icon="document-open-recent"),
                RibbonAction("Well Path", "visualization_add_well", icon="map"),
            ],
        )
        display_group = RibbonGroup(
            label="2D Display",
            actions=[
                RibbonAction("Wiggle + Density", "visualization_wiggle_density", icon="office-chart-line"),
                RibbonAction("Wiggle", "visualization_wiggle", icon="office-chart-line"),
                RibbonAction("Variable Density", "visualization_density", icon="view-grid"),
                RibbonAction("Fit", "visualization_fit", icon="zoom-fit-best"),
            ],
        )
        volume_group = RibbonGroup(
            label="3D Display",
            actions=[
                RibbonAction("Load Volume", "visualization_load_volume", icon="view-3d", accent=True),
                RibbonAction("Volume", "visualization_show_volume", icon="view-3d"),
                RibbonAction("Inline", "visualization_inline", icon="view-split-left-right"),
                RibbonAction("Crossline", "visualization_crossline", icon="view-split-top-bottom"),
                RibbonAction("Time Slice", "visualization_time_slice", icon="view-grid"),
            ],
        )
        geospatial_group = RibbonGroup(
            label="Satellite & Terrain",
            actions=[
                RibbonAction("Satellite", "visualization_satellite", icon="earth", accent=True),
                RibbonAction("3D Terrain", "visualization_terrain", icon="view-3d"),
            ],
        )
        interpretation_group = RibbonGroup(
            label="Interpretation",
            actions=[
                RibbonAction("Pick Horizon", "visualization_pick_horizon", icon="draw-freehand"),
                RibbonAction("Pick Fault", "visualization_pick_fault", icon="draw-line"),
                RibbonAction("Measure", "visualization_measure", icon="measure"),
                RibbonAction("Undo Pick", "visualization_undo_pick", icon="edit-undo"),
                RibbonAction("Stop", "visualization_stop_pick", icon="process-stop"),
            ],
        )
        qc_group = RibbonGroup(
            label="QC",
            actions=[
                RibbonAction("Bad Traces", "visualization_bad_traces", icon="dialog-warning", accent=True),
                RibbonAction("Noise Overlay", "visualization_noise_overlay", icon="view-statistics"),
                RibbonAction("AGC", "visualization_gain_agc", icon="view-statistics"),
                RibbonAction("Trace Balance", "visualization_gain_balance", icon="view-statistics"),
                RibbonAction("No Gain", "visualization_gain_none", icon="edit-clear"),
            ],
        )
        export_group = RibbonGroup(
            label="Export",
            actions=[
                RibbonAction("PNG", "visualization_export_png", icon="image-x-generic"),
                RibbonAction("GeoTIFF", "visualization_export_geotiff", icon="map"),
                RibbonAction("KML/KMZ", "visualization_export_kml", icon="earth"),
                RibbonAction("Shapefile", "visualization_export_shapefile", icon="map"),
                RibbonAction("HTML", "visualization_export_html", icon="text-html"),
                RibbonAction("PDF", "visualization_export_pdf", icon="application-pdf"),
                RibbonAction("Animation", "visualization_export_animation", icon="video-x-generic"),
            ],
        )
        return [file_group, display_group, volume_group, geospatial_group, interpretation_group, qc_group, export_group]
