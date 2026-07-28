from __future__ import annotations

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class _Provider(RibbonProvider):
    tab_id = ""
    groups: list[RibbonGroup] = []

    def ribbon_tab_id(self) -> str:
        return self.tab_id

    def build_ribbon_groups(self) -> list[RibbonGroup]:
        return self.groups


class GeodeticDataRibbonProvider(_Provider):
    tab_id = "geodetic_data"
    groups = [
        RibbonGroup("DC / Survey File", [
            RibbonAction("Open DC", "geodetic_open", icon="document-open", accent=True),
            RibbonAction("Examiner", "geodetic_examiner", icon="view-list-details"),
            RibbonAction("Text Results", "geodetic_text_results", icon="text-x-generic"),
        ]),
        RibbonGroup("Selected Fields", [
            RibbonAction("Export Text", "geodetic_export_text", icon="document-export"),
            RibbonAction("Export Excel", "geodetic_export_xlsx", icon="x-office-spreadsheet"),
        ]),
    ]


class GeodeticQcRibbonProvider(_Provider):
    tab_id = "geodetic_qc"
    groups = [
        RibbonGroup("Quality Control", [
            RibbonAction("Run QC", "geodetic_run_qc", icon="media-playback-start", accent=True),
            RibbonAction("QC & Graphs", "geodetic_qc_results", icon="view-statistics"),
        ]),
        RibbonGroup("Graph Pages", [
            RibbonAction("Previous", "geodetic_graph_prev", icon="go-previous"),
            RibbonAction("Next", "geodetic_graph_next", icon="go-next"),
            RibbonAction("Export Graphs", "geodetic_export_graphs", icon="document-export"),
        ]),
    ]


class GeodeticCoordinatesRibbonProvider(_Provider):
    tab_id = "geodetic_coordinates"
    groups = [
        RibbonGroup("Observations", [
            RibbonAction("Positions", "geodetic_positions", icon="map", accent=True),
            RibbonAction("Vectors", "geodetic_vectors", icon="transform-move"),
        ]),
        RibbonGroup("Reference & Equipment", [
            RibbonAction("Datum / CRS", "geodetic_datum_crs", icon="preferences-system"),
            RibbonAction("Equipment", "geodetic_equipment", icon="applications-engineering"),
        ]),
    ]


class GeodeticViewerRibbonProvider(_Provider):
    tab_id = "geodetic_viewer"
    groups = [
        RibbonGroup("Native Scientific View", [
            RibbonAction("2D Positions", "geodetic_view_2d", icon="map", accent=True),
            RibbonAction("3D Positions", "geodetic_view_3d", icon="view-3d"),
        ]),
        RibbonGroup("Geographic Context", [
            RibbonAction("Satellite", "geodetic_satellite", icon="earth"),
            RibbonAction("3D Terrain", "geodetic_terrain", icon="view-3d"),
        ]),
    ]


class GeodeticReportsRibbonProvider(_Provider):
    tab_id = "geodetic_reports"
    groups = [
        RibbonGroup("Reports & Export", [
            RibbonAction("QC PDF", "geodetic_report_pdf", icon="application-pdf", accent=True),
            RibbonAction("Excel", "geodetic_export_xlsx", icon="x-office-spreadsheet"),
            RibbonAction("Text", "geodetic_export_text", icon="text-x-generic"),
            RibbonAction("Graphs", "geodetic_export_graphs", icon="document-export"),
        ]),
    ]


def geodetic_providers() -> list[RibbonProvider]:
    return [
        GeodeticDataRibbonProvider(),
        GeodeticQcRibbonProvider(),
        GeodeticCoordinatesRibbonProvider(),
        GeodeticViewerRibbonProvider(),
        GeodeticReportsRibbonProvider(),
    ]
