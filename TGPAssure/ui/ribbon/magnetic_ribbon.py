from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class MagneticRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "magnetic"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup(
                "Magnetic Data",
                [
                    RibbonAction("Open Rover", "magnetic_open_rover", icon="document-open", accent=True),
                    RibbonAction("Open Base", "magnetic_open_base", icon="office-chart-line"),
                    RibbonAction("Boundary", "magnetic_open_boundary", icon="map"),
                    RibbonAction("Dataset", "magnetic_open", icon="view-dashboard"),
                ],
            ),
            RibbonGroup(
                "Quality Control",
                [
                    RibbonAction("Full QC", "magnetic_run_full", icon="media-playback-start", accent=True),
                    RibbonAction("Raw QC", "magnetic_run_raw", icon="view-statistics"),
                    RibbonAction("Processed QC", "magnetic_run_processed", icon="dialog-ok-apply"),
                    RibbonAction("Cancel", "magnetic_cancel", icon="process-stop"),
                ],
            ),
            RibbonGroup(
                "Processing",
                [
                    RibbonAction("Despike", "magnetic_despike", icon="edit-clear"),
                    RibbonAction("Diurnal", "magnetic_diurnal", icon="view-refresh"),
                    RibbonAction("Leveling", "magnetic_level", icon="transform-move"),
                    RibbonAction("Microlevel", "magnetic_microlevel", icon="transform-scale"),
                    RibbonAction("Grid", "magnetic_grid", icon="view-grid"),
                ],
            ),
            RibbonGroup(
                "Review and Export",
                [
                    RibbonAction("Map", "magnetic_map", icon="map"),
                    RibbonAction("Profiles", "magnetic_profile", icon="office-chart-line"),
                    RibbonAction("Export CSV", "magnetic_export_csv", icon="document-export"),
                    RibbonAction("PDF Report", "magnetic_report_pdf", icon="application-pdf"),
                    RibbonAction("Excel Report", "magnetic_report_xlsx", icon="x-office-spreadsheet"),
                ],
            ),
        ]
