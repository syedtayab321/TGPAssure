from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class ElectricalRibbonProvider(RibbonProvider):
    """Standalone Prosys II electrical/IP ribbon."""

    def ribbon_tab_id(self) -> str:
        return "electrical_prosys"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        small = "small"
        return [
            RibbonGroup("Prosys II", [
                RibbonAction("Open", "electrical_open_data", icon="document-open", accent=True, presentation=small),
                RibbonAction("Calc", "electrical_calculate", icon="view-refresh", accent=True, presentation=small),
                RibbonAction("Pseudo", "electrical_pseudosection", icon="view-statistics", presentation=small),
                RibbonAction("Profile", "electrical_profile", icon="office-chart-line", presentation=small),
            ]),
            RibbonGroup("QC", [
                RibbonAction("Filter", "electrical_prosys_filter", icon="preferences-system", presentation=small),
                RibbonAction("Reject", "electrical_prosys_reject", icon="edit-delete", presentation=small),
                RibbonAction("Median", "electrical_prosys_median", icon="view-refresh", presentation=small),
                RibbonAction("Sliding", "electrical_prosys_sliding", icon="view-refresh", presentation=small),
            ]),
            RibbonGroup("Topography", [
                RibbonAction("Topo", "electrical_prosys_topography", icon="map", presentation=small),
                RibbonAction("Elev", "electrical_prosys_elevation", icon="transform-move", presentation=small),
                RibbonAction("SP Drift", "electrical_sp_drift", icon="view-refresh", presentation=small),
                RibbonAction("Despike", "electrical_despike", icon="edit-clear", presentation=small),
            ]),
            RibbonGroup("Export", [
                RibbonAction("TXT", "electrical_export_csv", icon="document-export", accent=True, presentation=small),
                RibbonAction("RES2D", "electrical_export_res2dinv", icon="document-export", presentation=small),
                RibbonAction("RES3D", "electrical_export_res3dinv", icon="document-export", presentation=small),
                RibbonAction("Report", "electrical_report_pdf", icon="document-print", presentation=small),
            ]),
        ]


class IPWin2RibbonProvider(RibbonProvider):
    """Standalone VES/IP Studio ribbon, separate from Prosys II."""

    def ribbon_tab_id(self) -> str:
        return "electrical_ipwin2"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        small = "small"
        return [
            RibbonGroup("File", [
                RibbonAction("New", "electrical_ipi_new", icon="document-new", accent=True, presentation=small),
                RibbonAction("Open", "electrical_ipi_open", icon="document-open", presentation=small),
                RibbonAction("Save", "electrical_ipi_save", icon="document-save", presentation=small),
                RibbonAction("Print", "electrical_ipi_print", icon="document-print", presentation=small),
            ]),
            RibbonGroup("Edit", [
                RibbonAction("Info", "electrical_ipi_information", icon="dialog-information", presentation=small),
                RibbonAction("Curve", "electrical_ipi_edit_curve", icon="edit-table-cell", accent=True, presentation=small),
                RibbonAction("Copy", "electrical_ipi_copy_results", icon="edit-copy", presentation=small),
                RibbonAction("DZ", "electrical_ipi_dar_zarrouk", icon="office-chart-line", presentation=small),
            ]),
            RibbonGroup("Point", [
                RibbonAction("First", "electrical_ipi_first", icon="go-first", presentation=small),
                RibbonAction("Prev", "electrical_ipi_previous", icon="go-previous", presentation=small),
                RibbonAction("Next", "electrical_ipi_next", icon="go-next", presentation=small),
                RibbonAction("Last", "electrical_ipi_last", icon="go-last", presentation=small),
                RibbonAction("Invert", "electrical_ipi_inversion", icon="view-refresh", accent=True, presentation=small),
            ]),
            RibbonGroup("Model", [
                RibbonAction("New", "electrical_ipi_new_model", icon="document-new", presentation=small),
                RibbonAction("Opt", "electrical_ipi_inversion_options", icon="preferences-system", presentation=small),
                RibbonAction("Split", "electrical_ipi_split", icon="edit-table-cell-split", presentation=small),
                RibbonAction("Join", "electrical_ipi_join", icon="edit-table-cell-merge", presentation=small),
                RibbonAction("Fix H", "electrical_ipi_fix_h", icon="object-locked", presentation=small),
                RibbonAction("Min", "electrical_ipi_model_minimum", icon="go-down", presentation=small),
                RibbonAction("Max", "electrical_ipi_model_maximum", icon="go-up", presentation=small),
            ]),
            RibbonGroup("Section", [
                RibbonAction("Pseudo", "electrical_ipi_pseudosection", icon="view-statistics", presentation=small),
                RibbonAction("Res", "electrical_ipi_resistivity", icon="view-statistics", presentation=small),
                RibbonAction("Both", "electrical_ipi_both_sections", icon="view-statistics", accent=True, presentation=small),
                RibbonAction("Zoom+", "electrical_ipi_zoom_in", icon="zoom-in", presentation=small),
                RibbonAction("Zoom-", "electrical_ipi_zoom_out", icon="zoom-out", presentation=small),
                RibbonAction("Limits", "electrical_ipi_axes_limits", icon="zoom-fit-best", presentation=small),
                RibbonAction("Opt", "electrical_ipi_section_options", icon="preferences-system", presentation=small),
            ]),
            RibbonGroup("Tools", [
                RibbonAction("Info", "electrical_ipi_information", icon="dialog-information", presentation=small),
                RibbonAction("Move L", "electrical_ipi_move_left", icon="go-previous", presentation=small),
                RibbonAction("Move R", "electrical_ipi_move_right", icon="go-next", presentation=small),
                RibbonAction("Mirror", "electrical_ipi_mirror", icon="transform-move", presentation=small),
            ]),
            RibbonGroup("Options", [
                RibbonAction("Autosave", "electrical_ipi_options", icon="preferences-system", presentation=small),
                RibbonAction("Palette", "electrical_ipi_palette", icon="color-picker", presentation=small),
                RibbonAction("Invert", "electrical_ipi_invert_palette", icon="color-picker", presentation=small),
                RibbonAction("Auto", "electrical_ipi_auto_scale", icon="view-refresh", presentation=small),
                RibbonAction("Log", "electrical_ipi_log_scale", icon="view-refresh", presentation=small),
                RibbonAction("Fit", "electrical_ipi_fit_profile", icon="zoom-fit-best", presentation=small),
            ]),
            RibbonGroup("Windows", [
                RibbonAction("Classic", "electrical_ipi_classic_layout", icon="view-grid", accent=True, presentation=small),
                RibbonAction("Data", "electrical_ipi_data_window", icon="edit-table-cell", presentation=small),
                RibbonAction("Curve", "electrical_ipi_curve_window", icon="office-chart-line", presentation=small),
                RibbonAction("Sections", "electrical_ipi_section_window", icon="view-statistics", presentation=small),
                RibbonAction("Results", "electrical_ipi_results_window", icon="document-preview", presentation=small),
            ]),
        ]
