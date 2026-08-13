from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class SercelLogAnalysisRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "sercel_log_analysis"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("Daily Folder", [
                RibbonAction("Open Folder", "sercel_log_open", icon="folder-open", accent=True),
                RibbonAction("Reload", "sercel_log_reload", icon="view-refresh"),
            ]),
            RibbonGroup("SLX QC", [
                RibbonAction("Run QC", "sercel_log_qc", icon="media-playback-start"),
                RibbonAction("CRC CSV", "sercel_log_crc", icon="x-office-spreadsheet"),
                RibbonAction("Export Image", "sercel_log_export_image", icon="document-export"),
            ]),
        ]


class SercelInstrumentTestAnalysisRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "sercel_instrument_test_analysis"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("SITA Folder", [
                RibbonAction("Select Folder", "sita_open", icon="folder-open", accent=True),
                RibbonAction("Show Results", "sita_show", icon="view-statistics"),
            ]),
            RibbonGroup("Results", [
                RibbonAction("Sort Serial", "sita_sort", icon="view-sort-ascending"),
                RibbonAction("List Failures", "sita_failures", icon="dialog-warning"),
                RibbonAction("Export CSV", "sita_csv", icon="x-office-spreadsheet"),
                RibbonAction("Export Image", "sita_export_image", icon="document-export"),
            ]),
        ]


class TGPGroundForceLookRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "gflook"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("GF Files", [
                RibbonAction("Open Folder", "gflook_open_folder", icon="folder-open", accent=True),
                RibbonAction("Open File", "gflook_open_file", icon="document-open"),
                RibbonAction("Reload", "gflook_reload", icon="view-refresh"),
            ]),
            RibbonGroup("Analysis Pages", [
                RibbonAction("Page 1", "gflook_page1", icon="view-list-details"),
                RibbonAction("Page 2", "gflook_page2", icon="view-list-details"),
                RibbonAction("Page 3", "gflook_page3", icon="view-statistics"),
                RibbonAction("Page 4", "gflook_page4", icon="applications-graphics"),
                RibbonAction("File Info", "gflook_file_info", icon="dialog-information"),
            ]),
            RibbonGroup("Ground Force QC", [
                RibbonAction("Run QC", "gflook_run_qc", icon="media-playback-start", accent=True),
                RibbonAction("QC Listing", "gflook_qc_listing", icon="x-office-spreadsheet"),
                RibbonAction("Export Image", "gflook_export_image", icon="document-export"),
            ]),
            RibbonGroup("Outputs", [
                RibbonAction("KMZ", "gflook_export_kmz", icon="applications-internet"),
                RibbonAction("Shape File", "gflook_export_shp", icon="map"),
                RibbonAction("SEG-Y", "gflook_convert_segy", icon="media-tape"),
            ]),
        ]
