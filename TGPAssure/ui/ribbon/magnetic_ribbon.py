from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class MagneticRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "magnetic_enmag"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup(
                "Data",
                [
                    RibbonAction("Open Folder", "magnetic_open_folder", icon="folder-open", accent=True),
                    RibbonAction("Open Rover", "magnetic_open_rover", icon="document-open"),
                    RibbonAction("Open Base", "magnetic_open_base", icon="office-chart-line"),
                    RibbonAction("Boundary", "magnetic_open_boundary", icon="map"),
                ],
            ),
            RibbonGroup(
                "Display",
                [
                    RibbonAction("Draw", "magnetic_grid", icon="view-grid", accent=True),
                    RibbonAction("Profile", "magnetic_profile", icon="office-chart-line"),
                    RibbonAction("Map", "magnetic_map", icon="map"),
                ],
            ),
            RibbonGroup(
                "Processing",
                [
                    RibbonAction("Despike", "magnetic_despike", icon="edit-clear"),
                    RibbonAction("Diurnal", "magnetic_diurnal", icon="view-refresh"),
                    RibbonAction("Level", "magnetic_level", icon="transform-move"),
                    RibbonAction("Microlevel", "magnetic_microlevel", icon="transform-scale"),
                ],
            ),
            RibbonGroup(
                "Export",
                [
                    RibbonAction("Export CSV", "magnetic_export_csv", icon="document-export", accent=True),
                    RibbonAction("Report", "magnetic_report_pdf", icon="document-print"),
                ],
            ),
        ]
