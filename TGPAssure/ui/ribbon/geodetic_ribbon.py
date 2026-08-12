from __future__ import annotations

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class GeodeticDcExaminerRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "geodetic_data"

    def build_ribbon_groups(self) -> list[RibbonGroup]:
        return [
            RibbonGroup("File", [
                RibbonAction("Open", "geodetic_open", icon="document-open", accent=True),
                RibbonAction("Text Results", "geodetic_text_results", icon="text-x-generic"),
                RibbonAction("Graphs", "geodetic_qc_results", icon="view-statistics", accent=True),
            ]),
            RibbonGroup("Output", [
                RibbonAction("Export Text", "geodetic_export_text", icon="document-export"),
                RibbonAction("Export XLS", "geodetic_export_xlsx", icon="x-office-spreadsheet"),
                RibbonAction("Export Graph", "geodetic_export_graphs", icon="image-x-generic"),
            ]),
            RibbonGroup("Graph Pages", [
                RibbonAction("Last Page", "geodetic_graph_prev", icon="go-previous", accent=True),
                RibbonAction("Next Page", "geodetic_graph_next", icon="go-next", accent=True),
            ]),
        ]


def geodetic_providers() -> list[RibbonProvider]:
    return [GeodeticDcExaminerRibbonProvider()]
