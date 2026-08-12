from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class ElectricalRibbonProvider(RibbonProvider):
    """Electrical ribbon reduced to Prosys II only."""

    def ribbon_tab_id(self) -> str:
        return "electrical_prosys"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("Prosys II", [
                RibbonAction("Open Prosys", "electrical_open", icon="electrical", accent=True),
                RibbonAction("Open Data", "electrical_open_data", icon="document-open"),
                RibbonAction("Refresh Fields", "electrical_calculate", icon="view-refresh"),
            ]),
            RibbonGroup("Processing", [
                RibbonAction("Range Filter", "electrical_prosys_filter", icon="preferences-system", accent=True),
                RibbonAction("Reject Rows", "electrical_prosys_reject", icon="edit-delete"),
                RibbonAction("Median Avg", "electrical_prosys_median", icon="view-refresh"),
                RibbonAction("Sliding Avg", "electrical_prosys_sliding", icon="view-refresh"),
            ]),
            RibbonGroup("Topography", [
                RibbonAction("Insert Topo", "electrical_prosys_topography", icon="map", accent=True),
                RibbonAction("Elevation Offset", "electrical_prosys_elevation", icon="measure"),
            ]),
            RibbonGroup("Export", [
                RibbonAction("TXT", "electrical_export_csv", icon="document-export", accent=True),
                RibbonAction("RES2DINV", "electrical_export_res2dinv", icon="document-export"),
                RibbonAction("RES3DINV", "electrical_export_res3dinv", icon="document-export"),
            ]),
        ]
