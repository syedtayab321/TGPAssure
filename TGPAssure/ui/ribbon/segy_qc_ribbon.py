from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SegyQcRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "segy_qc"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        data_group = RibbonGroup(
            label="View → QC → Re-View",
            actions=[
                RibbonAction("Open Raw", "segy_open_file", icon="document-open", accent=True),
                RibbonAction("View Raw", "segy_view_raw", icon="view-preview"),
                RibbonAction("Select Post-QC", "segy_select_post_qc", icon="document-open-recent"),
                RibbonAction("View Post-QC", "segy_view_post_qc", icon="view-preview"),
                RibbonAction("Compare", "segy_compare_pre_post", icon="view-split-left-right"),
                RibbonAction("Select 4D Base", "segy_select_base", icon="document-open-recent"),
            ],
        )
        run_group = RibbonGroup(
            label="Run Control",
            actions=[
                RibbonAction("Run All QC", "segy_run_qc", icon="media-playback-start", accent=True),
                RibbonAction("Cancel", "segy_cancel_qc", icon="process-stop"),
                RibbonAction("Results", "segy_view_results", icon="view-statistics"),
            ],
        )
        prestack_group = RibbonGroup(
            label="Pre-Stack Processing QC",
            actions=[
                RibbonAction("Residual Statics", "segy_stage_residual_statics", icon="transform-move"),
                RibbonAction("Velocity", "segy_stage_velocity", icon="office-chart-line"),
                RibbonAction("NMO", "segy_stage_nmo", icon="transform-scale"),
                RibbonAction("Stack", "segy_stage_stack", icon="view-list-tree"),
            ],
        )
        imaging_group = RibbonGroup(
            label="Imaging and 4D QC",
            actions=[
                RibbonAction("Migration", "segy_stage_migration", icon="view-3d"),
                RibbonAction("Attributes", "segy_stage_attribute", icon="view-statistics"),
                RibbonAction("4D Repeatability", "segy_stage_repeatability", icon="view-refresh"),
            ],
        )
        output_group = RibbonGroup(
            label="Setup and Reports",
            actions=[
                RibbonAction("Profiles", "segy_edit_profile", icon="preferences-system"),
                RibbonAction("Dashboard", "segy_open_dashboard", icon="view-dashboard"),
                RibbonAction("PDF", "segy_generate_pdf", icon="application-pdf"),
                RibbonAction("XLSX", "segy_generate_xlsx", icon="x-office-spreadsheet"),
            ],
        )
        return [data_group, run_group, prestack_group, imaging_group, output_group]
