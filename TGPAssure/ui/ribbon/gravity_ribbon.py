from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class GravityRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "gravity"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        """Main Gravity ribbon commands.

        The in-workspace File/Edit/View/Oasis title strip was removed from the
        dashboard. These actions now live in the main ribbon, matching the rest
        of TGPAssure and keeping the workspace clean and responsive.
        """
        return [
            RibbonGroup("Gravity Data", [
                RibbonAction("Open Workspace", "gravity_open", icon="folder-open", accent=True),
                RibbonAction("Open Observations", "gravity_open_observations", icon="document-open"),
                RibbonAction("Open Base", "gravity_open_base", icon="office-chart-line"),
            ]),
            RibbonGroup("Reduction / QC", [
                RibbonAction("Reduction", "gravity_reduce", icon="view-refresh", accent=True),
                RibbonAction("Run QC", "gravity_run_full", icon="media-playback-start"),
                RibbonAction("Cancel", "gravity_cancel", icon="process-stop"),
            ]),
            RibbonGroup("Grid / Map", [
                RibbonAction("Create Grid", "gravity_grid", icon="view-grid", accent=True),
                RibbonAction("Map", "gravity_map", icon="map"),
                RibbonAction("Profile", "gravity_profile", icon="office-chart-line"),
                RibbonAction("2D View", "gravity_view_2d", icon="view-restore"),
            ]),
            RibbonGroup("Database", [
                RibbonAction("Database", "gravity_database", icon="view-list-details"),
                RibbonAction("Channels", "gravity_channels", icon="format-list-unordered"),
                RibbonAction("Layers", "gravity_layers", icon="layer-visible-on"),
            ]),
            RibbonGroup("Output", [
                RibbonAction("Export CSV", "gravity_export_csv", icon="document-export"),
                RibbonAction("PDF Report", "gravity_report_pdf", icon="application-pdf", accent=True),
                RibbonAction("Excel Report", "gravity_report_xlsx", icon="x-office-spreadsheet"),
            ]),
        ]
