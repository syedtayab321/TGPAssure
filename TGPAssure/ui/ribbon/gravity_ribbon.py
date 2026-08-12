from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class GravityRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "gravity"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("Oasis Gravity", [
                RibbonAction("Open Observations", "gravity_open_observations", icon="document-open", accent=True),
                RibbonAction("Open Base", "gravity_open_base", icon="office-chart-line"),
                RibbonAction("Workspace", "gravity_open", icon="view-dashboard"),
            ]),
            RibbonGroup("Processing", [
                RibbonAction("Reduction", "gravity_reduce", icon="view-refresh", accent=True),
                RibbonAction("Create Grid", "gravity_grid", icon="view-grid"),
                RibbonAction("Run QC", "gravity_run_full", icon="media-playback-start"),
            ]),
            RibbonGroup("Maps / Profiles", [
                RibbonAction("Map", "gravity_map", icon="map", accent=True),
                RibbonAction("Profile", "gravity_profile", icon="office-chart-line"),
                RibbonAction("2D View", "gravity_view_2d", icon="view-restore"),
            ]),
            RibbonGroup("Output", [
                RibbonAction("Export CSV", "gravity_export_csv", icon="document-export"),
                RibbonAction("Report", "gravity_report_pdf", icon="application-pdf", accent=True),
            ]),
        ]
