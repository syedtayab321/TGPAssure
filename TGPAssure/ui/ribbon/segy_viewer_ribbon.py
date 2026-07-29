from __future__ import annotations
from typing import List
from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SegyViewerRibbonProvider(RibbonProvider):
    """Combined SEG-Y viewer + SEG-Y QC ribbon.

    The separate SEG-Y QC ribbon subtab is intentionally folded into this provider
    so users have one SEG-Y workspace, similar to the SEG-D workflow.
    """

    def ribbon_tab_id(self) -> str:
        return "segy_viewer"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("File / View", [
                RibbonAction("Open SEG-Y", "segy_open_file", icon="seg-y", accent=True),
                RibbonAction("Open 2D/3D", "segy_open_2d3d", icon="view-3d"),
                RibbonAction("Fit", "segy_viewer_fit", icon="zoom-fit-best"),
                RibbonAction("Export PNG", "segy_viewer_export_image", icon="document-save"),
            ]),
            RibbonGroup("Display", [
                RibbonAction("Wiggle", "segy_viewer_wiggle", icon="office-chart-line"),
                RibbonAction("Variable Area", "segy_viewer_va", icon="view-grid"),
                RibbonAction("Variable Density", "segy_viewer_vd", icon="view-grid"),
                RibbonAction("Color Density", "segy_viewer_color", icon="view-grid"),
            ]),
            RibbonGroup("Inspect", [
                RibbonAction("Headers", "segy_viewer_headers", icon="document-properties"),
                RibbonAction("Trace Analysis", "segy_viewer_trace_analysis", icon="view-statistics"),
                RibbonAction("View Raw", "segy_view_raw", icon="view-preview"),
                RibbonAction("Compare", "segy_compare_pre_post", icon="view-split-left-right"),
            ]),
            RibbonGroup("QC", [
                RibbonAction("Run QC", "segy_run_qc", icon="media-playback-start", accent=True),
                RibbonAction("Cancel", "segy_cancel_qc", icon="process-stop"),
                RibbonAction("Results", "segy_view_results", icon="view-statistics"),
                RibbonAction("Profiles", "segy_edit_profile", icon="preferences-system"),
            ]),
            RibbonGroup("Post-QC / Reports", [
                RibbonAction("Select Post-QC", "segy_select_post_qc", icon="document-open-recent"),
                RibbonAction("View Post-QC", "segy_view_post_qc", icon="view-preview"),
                RibbonAction("PDF", "segy_generate_pdf", icon="application-pdf"),
                RibbonAction("XLSX", "segy_generate_xlsx", icon="x-office-spreadsheet"),
            ]),
        ]
