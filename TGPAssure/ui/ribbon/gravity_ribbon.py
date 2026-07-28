from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class GravityRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "gravity"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("Gravity Data", [
                RibbonAction("Observations", "gravity_open_observations", icon="document-open", accent=True),
                RibbonAction("Base Station", "gravity_open_base", icon="office-chart-line"),
                RibbonAction("Dashboard", "gravity_open", icon="view-dashboard"),
            ]),
            RibbonGroup("Quality Control", [
                RibbonAction("Full QC", "gravity_run_full", icon="media-playback-start", accent=True),
                RibbonAction("Field QC", "gravity_run_field", icon="view-statistics"),
                RibbonAction("Final QC", "gravity_run_final", icon="dialog-ok-apply"),
                RibbonAction("Cancel", "gravity_cancel", icon="process-stop"),
            ]),
            RibbonGroup("Reduction", [
                RibbonAction("Standard Reduction", "gravity_reduce", icon="view-refresh", accent=True),
                RibbonAction("Grid", "gravity_grid", icon="view-grid"),
            ]),
            RibbonGroup("Review and Export", [
                RibbonAction("Anomaly Map", "gravity_map", icon="map"),
                RibbonAction("Profiles", "gravity_profile", icon="office-chart-line"),
                RibbonAction("Export CSV", "gravity_export_csv", icon="document-export"),
                RibbonAction("PDF Report", "gravity_report_pdf", icon="application-pdf"),
                RibbonAction("Excel Report", "gravity_report_xlsx", icon="x-office-spreadsheet"),
            ]),
        ]
