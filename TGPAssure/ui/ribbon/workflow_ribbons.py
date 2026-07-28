from __future__ import annotations

"""Contextual secondary-ribbon providers for the six top-level workflows."""

from ui.ribbon.ribbon_provider import RibbonAction, RibbonGroup, RibbonProvider


class _Provider(RibbonProvider):
    tab_id = ""
    groups: list[RibbonGroup] = []

    def ribbon_tab_id(self) -> str:
        return self.tab_id

    def build_ribbon_groups(self) -> list[RibbonGroup]:
        return self.groups


class MagneticDataRibbonProvider(_Provider):
    tab_id = "magnetic_data"
    groups = [
        RibbonGroup("Data", [
            RibbonAction("Open Rover", "magnetic_open_rover", icon="document-open", accent=True),
            RibbonAction("Open Base", "magnetic_open_base", icon="office-chart-line"),
            RibbonAction("Boundary", "magnetic_open_boundary", icon="map"),
            RibbonAction("Dashboard", "magnetic_open", icon="view-dashboard"),
        ]),
        RibbonGroup("Raw Review", [
            RibbonAction("2D Map", "magnetic_view_2d", icon="map"),
            RibbonAction("Profile", "magnetic_profile", icon="office-chart-line"),
            RibbonAction("Satellite", "magnetic_satellite", icon="earth"),
        ]),
    ]


class MagneticQcRibbonProvider(_Provider):
    tab_id = "magnetic_qc"
    groups = [
        RibbonGroup("Quality Control", [
            RibbonAction("Full QC", "magnetic_run_full", icon="media-playback-start", accent=True),
            RibbonAction("Raw QC", "magnetic_run_raw", icon="view-statistics"),
            RibbonAction("Processed QC", "magnetic_run_processed", icon="dialog-ok-apply"),
            RibbonAction("Cancel", "magnetic_cancel", icon="process-stop"),
        ]),
        RibbonGroup("Review", [
            RibbonAction("2D Data", "magnetic_view_2d", icon="map"),
            RibbonAction("3D Data", "magnetic_view_3d", icon="view-3d"),
            RibbonAction("Satellite", "magnetic_satellite", icon="earth"),
            RibbonAction("3D Terrain", "magnetic_terrain", icon="view-3d"),
        ]),
    ]


class MagneticProcessingRibbonProvider(_Provider):
    tab_id = "magnetic_processing"
    groups = [
        RibbonGroup("Processing", [
            RibbonAction("Despike", "magnetic_despike", icon="edit-clear"),
            RibbonAction("Diurnal", "magnetic_diurnal", icon="view-refresh"),
            RibbonAction("Leveling", "magnetic_level", icon="transform-move"),
            RibbonAction("Microlevel", "magnetic_microlevel", icon="transform-scale"),
            RibbonAction("Grid", "magnetic_grid", icon="view-grid"),
        ]),
        RibbonGroup("Post-Process Review", [
            RibbonAction("2D Data", "magnetic_view_2d", icon="map"),
            RibbonAction("3D Data", "magnetic_view_3d", icon="view-3d"),
            RibbonAction("Profiles", "magnetic_profile", icon="office-chart-line"),
            RibbonAction("3D Terrain", "magnetic_terrain", icon="view-3d"),
        ]),
    ]


class MagneticViewerRibbonProvider(_Provider):
    tab_id = "magnetic_viewer"
    groups = [
        RibbonGroup("Native Scientific View", [
            RibbonAction("2D Data", "magnetic_view_2d", icon="map", accent=True),
            RibbonAction("3D Data", "magnetic_view_3d", icon="view-3d"),
            RibbonAction("Profiles", "magnetic_profile", icon="office-chart-line"),
        ]),
        RibbonGroup("Geographic Context", [
            RibbonAction("Satellite", "magnetic_satellite", icon="earth"),
            RibbonAction("3D Terrain", "magnetic_terrain", icon="view-3d"),
        ]),
    ]


class MagneticReportsRibbonProvider(_Provider):
    tab_id = "magnetic_reports"
    groups = [
        RibbonGroup("Export", [RibbonAction("Export CSV", "magnetic_export_csv", icon="document-export")]),
        RibbonGroup("QC Reports", [
            RibbonAction("PDF Report", "magnetic_report_pdf", icon="application-pdf", accent=True),
            RibbonAction("Excel Report", "magnetic_report_xlsx", icon="x-office-spreadsheet"),
        ]),
    ]


class GravityDataRibbonProvider(_Provider):
    tab_id = "gravity_data"
    groups = [
        RibbonGroup("Data", [
            RibbonAction("Observations", "gravity_open_observations", icon="document-open", accent=True),
            RibbonAction("Base Station", "gravity_open_base", icon="office-chart-line"),
            RibbonAction("Dashboard", "gravity_open", icon="view-dashboard"),
        ]),
        RibbonGroup("Raw Review", [
            RibbonAction("2D Map", "gravity_view_2d", icon="map"),
            RibbonAction("Profile", "gravity_profile", icon="office-chart-line"),
            RibbonAction("Satellite", "gravity_satellite", icon="earth"),
        ]),
    ]


class GravityQcRibbonProvider(_Provider):
    tab_id = "gravity_qc"
    groups = [RibbonGroup("Quality Control", [
        RibbonAction("Full QC", "gravity_run_full", icon="media-playback-start", accent=True),
        RibbonAction("Field QC", "gravity_run_field", icon="view-statistics"),
        RibbonAction("Final QC", "gravity_run_final", icon="dialog-ok-apply"),
        RibbonAction("Cancel", "gravity_cancel", icon="process-stop"),
    ])]


class GravityProcessingRibbonProvider(_Provider):
    tab_id = "gravity_processing"
    groups = [RibbonGroup("Reduction", [
        RibbonAction("Standard Reduction", "gravity_reduce", icon="view-refresh", accent=True),
        RibbonAction("Grid", "gravity_grid", icon="view-grid"),
    ])]


class GravityViewerRibbonProvider(_Provider):
    tab_id = "gravity_viewer"
    groups = [RibbonGroup("Unified Visualization", [
        RibbonAction("2D Anomaly", "gravity_view_2d", icon="map", accent=True),
        RibbonAction("3D Terrain", "gravity_view_3d", icon="view-3d"),
        RibbonAction("Satellite", "gravity_satellite", icon="earth"),
        RibbonAction("Profiles", "gravity_profile", icon="office-chart-line"),
    ])]


class GravityReportsRibbonProvider(_Provider):
    tab_id = "gravity_reports"
    groups = [
        RibbonGroup("Export", [RibbonAction("Export CSV", "gravity_export_csv", icon="document-export")]),
        RibbonGroup("QC Reports", [
            RibbonAction("PDF Report", "gravity_report_pdf", icon="application-pdf", accent=True),
            RibbonAction("Excel Report", "gravity_report_xlsx", icon="x-office-spreadsheet"),
        ]),
    ]


class ElectricalDataRibbonProvider(_Provider):
    tab_id = "electrical_data"
    groups = [
        RibbonGroup("Data", [
            RibbonAction("Open Data", "electrical_open_data", icon="electrical", accent=True),
            RibbonAction("Dashboard", "electrical_open", icon="view-dashboard"),
            RibbonAction("Calculate Fields", "electrical_calculate", icon="view-refresh"),
        ]),
        RibbonGroup("Methods", [
            RibbonAction("ERT", "electrical_method_ert", icon="view-grid"),
            RibbonAction("VES", "electrical_method_ves", icon="office-chart-line"),
            RibbonAction("Profiling", "electrical_method_profiling", icon="measure"),
            RibbonAction("TDIP", "electrical_method_tdip", icon="electrical-ip"),
            RibbonAction("FDIP", "electrical_method_fdip", icon="office-chart-bar"),
            RibbonAction("SIP", "electrical_method_sip", icon="office-chart-bar"),
            RibbonAction("SP", "electrical_method_sp", icon="electrical-sp"),
        ]),
    ]


class ElectricalQcRibbonProvider(_Provider):
    tab_id = "electrical_qc"
    groups = [RibbonGroup("Quality Control", [
        RibbonAction("Run Full QC", "electrical_run_qc", icon="media-playback-start", accent=True),
        RibbonAction("QC Thresholds", "electrical_thresholds", icon="preferences-system"),
        RibbonAction("QC Results", "electrical_results", icon="dialog-ok-apply"),
    ])]


class ElectricalProcessingRibbonProvider(_Provider):
    tab_id = "electrical_processing"
    groups = [RibbonGroup("Processing", [
        RibbonAction("SP Drift Correct", "electrical_sp_drift", icon="view-refresh", accent=True),
        RibbonAction("Auditable Despike", "electrical_despike", icon="edit-clear"),
        RibbonAction("Pseudosection", "electrical_pseudosection", icon="view-statistics"),
        RibbonAction("Profile / Curve", "electrical_profile", icon="office-chart-line"),
    ])]


class ElectricalViewerRibbonProvider(_Provider):
    tab_id = "electrical_viewer"
    groups = [
        RibbonGroup("Native Scientific View", [
            RibbonAction("2D Data", "electrical_view_2d", icon="view-statistics", accent=True),
            RibbonAction("3D Data", "electrical_view_3d", icon="view-3d"),
            RibbonAction("Pseudosection", "electrical_pseudosection", icon="view-statistics"),
            RibbonAction("Profile / Curve", "electrical_profile", icon="office-chart-line"),
        ]),
        RibbonGroup("Geographic Context", [
            RibbonAction("Satellite", "electrical_satellite", icon="earth"),
            RibbonAction("3D Terrain", "electrical_terrain", icon="view-3d"),
        ]),
    ]


class ElectricalReportsRibbonProvider(_Provider):
    tab_id = "electrical_reports"
    groups = [
        RibbonGroup("Export", [RibbonAction("Export CSV", "electrical_export_csv", icon="document-export")]),
        RibbonGroup("QC Reports", [
            RibbonAction("PDF Report", "electrical_report_pdf", icon="application-pdf", accent=True),
            RibbonAction("Excel Report", "electrical_report_xlsx", icon="x-office-spreadsheet"),
        ]),
    ]


class VibroseisDataRibbonProvider(_Provider):
    tab_id = "vibroseis_data"
    groups = [
        RibbonGroup("Workspace", [
            RibbonAction("Open Vibroseis", "vibroseis_open", icon="media-playback-start", accent=True),
            RibbonAction("Load Telemetry", "vibroseis_load", icon="document-open"),
        ]),
        RibbonGroup("Source Design", [
            RibbonAction("Sweep Designer", "vibroseis_sweep", icon="view-statistics"),
            RibbonAction("Generate Sweep", "vibroseis_generate", icon="media-playback-start"),
            RibbonAction("Export Pilot", "vibroseis_export_pilot", icon="document-save"),
        ]),
    ]


class VibroseisQcRibbonProvider(_Provider):
    tab_id = "vibroseis_qc"
    groups = [
        RibbonGroup("Source QC", [
            RibbonAction("Signal QC", "vibroseis_signal_qc", icon="dialog-ok-apply", accent=True),
            RibbonAction("Correlation", "vibroseis_correlation", icon="view-statistics"),
            RibbonAction("Ground Force", "vibroseis_ground_force", icon="view-statistics"),
        ]),
        RibbonGroup("VAPS / Field Vib QC", [
            RibbonAction("Load VAPS/H26", "vibroseis_load_vaps", icon="document-open", accent=True),
            RibbonAction("VAPS QC", "vibroseis_vaps_qc", icon="view-statistics"),
        ]),
    ]


class VibroseisViewerRibbonProvider(_Provider):
    tab_id = "vibroseis_viewer"
    groups = [RibbonGroup("Unified Visualization", [
        RibbonAction("2D Signals", "vibroseis_view_2d", icon="office-chart-line", accent=True),
        RibbonAction("3D Terrain", "vibroseis_view_3d", icon="view-3d"),
        RibbonAction("Satellite", "vibroseis_satellite", icon="earth"),
    ])]


class VibroseisPlanningRibbonProvider(_Provider):
    tab_id = "vibroseis_planning"
    groups = [RibbonGroup("Planning & Output", [
        RibbonAction("Productivity", "vibroseis_productivity", icon="view-statistics", accent=True),
        RibbonAction("Export Pilot", "vibroseis_export_pilot", icon="document-save"),
    ])]



class SegdScannerRibbonProvider(_Provider):
    tab_id = "segd_scanner"
    groups = [
        RibbonGroup("428 / SEG-D Header Audit", [
            RibbonAction("Scan File", "segd_scanner_open", icon="document-open", accent=True),
            RibbonAction("Scan Folder", "segd_scanner_folder", icon="folder"),
            RibbonAction("Export CSV", "segd_scanner_export", icon="document-export"),
        ]),
        RibbonGroup("Review", [
            RibbonAction("Results", "segd_scanner_results", icon="view-list-details"),
            RibbonAction("Guide", "segd_scanner_guide", icon="help-contents"),
        ]),
    ]


class ReceiverQcRibbonProvider(_Provider):
    tab_id = "receiver_qc"
    groups = [
        RibbonGroup("SMT / Geophone Import", [
            RibbonAction("Open SMT", "receiver_open", icon="document-open", accent=True),
            RibbonAction("Run QC", "receiver_run_qc", icon="media-playback-start"),
            RibbonAction("Export CSV", "receiver_export", icon="document-export"),
        ]),
        RibbonGroup("Review", [
            RibbonAction("Records", "receiver_records", icon="view-list-details"),
            RibbonAction("Failures", "receiver_failures", icon="dialog-warning"),
            RibbonAction("Limits", "receiver_limits", icon="preferences-system"),
            RibbonAction("Statistics", "receiver_statistics", icon="view-statistics"),
        ]),
    ]


class UpholeRibbonProvider(_Provider):
    tab_id = "uphole"
    groups = [
        RibbonGroup("Uphole Data", [
            RibbonAction("Open File", "uphole_open", icon="document-open", accent=True),
            RibbonAction("Open Folder", "uphole_open_folder", icon="folder"),
            RibbonAction("Interpret", "uphole_interpret", icon="media-playback-start"),
            RibbonAction("Export CSV", "uphole_export", icon="document-export"),
        ]),
        RibbonGroup("Review", [
            RibbonAction("Assignments", "uphole_assignments", icon="view-list-details"),
            RibbonAction("Time-Depth", "uphole_time_depth", icon="office-chart-line"),
            RibbonAction("Layers", "uphole_layers", icon="view-statistics"),
            RibbonAction("Guide", "uphole_guide", icon="help-contents"),
        ]),
    ]


def workflow_providers() -> list[RibbonProvider]:
    return [
        MagneticDataRibbonProvider(), MagneticQcRibbonProvider(), MagneticProcessingRibbonProvider(),
        MagneticViewerRibbonProvider(), MagneticReportsRibbonProvider(),
        GravityDataRibbonProvider(), GravityQcRibbonProvider(), GravityProcessingRibbonProvider(),
        GravityViewerRibbonProvider(), GravityReportsRibbonProvider(),
        ElectricalDataRibbonProvider(), ElectricalQcRibbonProvider(), ElectricalProcessingRibbonProvider(),
        ElectricalViewerRibbonProvider(), ElectricalReportsRibbonProvider(),
        VibroseisDataRibbonProvider(), VibroseisQcRibbonProvider(), VibroseisViewerRibbonProvider(),
        VibroseisPlanningRibbonProvider(),
        SegdScannerRibbonProvider(), ReceiverQcRibbonProvider(), UpholeRibbonProvider(),
    ]
