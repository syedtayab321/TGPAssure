from __future__ import annotations

from typing import List

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class ElectricalRibbonProvider(RibbonProvider):
    def ribbon_tab_id(self) -> str:
        return "electrical"

    def build_ribbon_groups(self) -> List[RibbonGroup]:
        return [
            RibbonGroup("Electrical Data", [
                RibbonAction("Open Data", "electrical_open_data", icon="electrical", accent=True),
                RibbonAction("Dashboard", "electrical_open", icon="view-dashboard"),
                RibbonAction("Calculate Fields", "electrical_calculate", icon="view-refresh"),
            ]),
            RibbonGroup("Sub-Methods", [
                RibbonAction("ERT", "electrical_method_ert", icon="view-grid", accent=True),
                RibbonAction("VES", "electrical_method_ves", icon="office-chart-line"),
                RibbonAction("Resistivity Profile", "electrical_method_profiling", icon="measure"),
                RibbonAction("TDIP", "electrical_method_tdip", icon="electrical-ip"),
                RibbonAction("FDIP", "electrical_method_fdip", icon="office-chart-bar"),
                RibbonAction("SIP / Complex R", "electrical_method_sip", icon="office-chart-bar"),
                RibbonAction("Self-Potential", "electrical_method_sp", icon="electrical-sp"),
                RibbonAction("Mise-à-la-Masse", "electrical_method_malm", icon="map"),
                RibbonAction("Equipotential", "electrical_method_equipotential", icon="view-statistics"),
                RibbonAction("Telluric", "electrical_method_telluric", icon="electrical-sp"),
            ]),
            RibbonGroup("Quality Control", [
                RibbonAction("Run Full QC", "electrical_run_qc", icon="media-playback-start", accent=True),
                RibbonAction("QC Thresholds", "electrical_thresholds", icon="preferences-system"),
                RibbonAction("QC Results", "electrical_results", icon="dialog-ok-apply"),
            ]),
            RibbonGroup("Processing & Review", [
                RibbonAction("SP Drift Correct", "electrical_sp_drift", icon="view-refresh", accent=True),
                RibbonAction("Auditable Despike", "electrical_despike", icon="edit-clear"),
                RibbonAction("Pseudosection", "electrical_pseudosection", icon="view-statistics"),
                RibbonAction("Profile / Curve", "electrical_profile", icon="office-chart-line"),
            ]),
            RibbonGroup("Export & Report", [
                RibbonAction("Export CSV", "electrical_export_csv", icon="document-export", accent=True),
                RibbonAction("PDF Report", "electrical_report_pdf", icon="application-pdf"),
                RibbonAction("Excel Report", "electrical_report_xlsx", icon="x-office-spreadsheet"),
            ]),
        ]
