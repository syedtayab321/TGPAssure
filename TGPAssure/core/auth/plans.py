from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FeatureDef:
    key: str
    module: str
    title: str
    description: str
    monthly_pkr: int


@dataclass(frozen=True)
class PlanDef:
    key: str
    title: str
    description: str
    monthly_pkr: int
    features: tuple[str, ...]
    selectable: bool = True


FEATURES: tuple[FeatureDef, ...] = (
    FeatureDef("seismic.segd", "seismic", "SEG-D Viewer", "Open and inspect SEG-D/field records.", 12000),
    FeatureDef("seismic.viewer", "seismic", "SEG-Y / 2D Viewer", "Open SEG-Y and use 2D/3D seismic visualization.", 18000),
    FeatureDef("seismic.converter", "seismic", "Converters", "SEG-Y/SEG-D conversion and export tools.", 12000),
    FeatureDef("seismic.receiver", "seismic", "Receiver QC", "Receiver, geophone and instrument QC workflows.", 11000),
    FeatureDef("seismic.uphole", "seismic", "Uphole", "Uphole time-depth and velocity QC.", 9000),
    FeatureDef("seismic.scanner", "seismic", "428 Header Scanner", "Header scanning and acquisition log review.", 9000),

    FeatureDef("magnetic.data", "magnetic", "Magnetic Data", "Rover, base and boundary import.", 10000),
    FeatureDef("magnetic.qc", "magnetic", "Magnetic QC", "Field, base, tie-line and acquisition QC.", 18000),
    FeatureDef("magnetic.processing", "magnetic", "Magnetic Processing", "Despike, diurnal, leveling, grid and profile outputs.", 24000),
    FeatureDef("magnetic.viewer", "magnetic", "Magnetic 2D/3D & Satellite", "Maps, profiles, spatial and terrain views.", 15000),
    FeatureDef("magnetic.reports", "magnetic", "Magnetic Reports", "PDF/XLSX reports and client outputs.", 9000),

    FeatureDef("electrical.data", "electrical", "Electrical Data", "ERT, VES, profiling, TDIP, FDIP, SIP and SP import.", 10000),
    FeatureDef("electrical.qc", "electrical", "Electrical/IP QC", "Contact, stacking, reciprocal, IP decay and method QC.", 19000),
    FeatureDef("electrical.processing", "electrical", "Electrical Processing", "SP drift, despike, pseudosection and preprocessing tools.", 21000),
    FeatureDef("electrical.viewer", "electrical", "Electrical 2D/3D & Satellite", "Native, map and terrain views.", 14000),
    FeatureDef("electrical.reports", "electrical", "Electrical Reports", "Reports and interpreted export products.", 8000),

    FeatureDef("gravity.data", "gravity", "Gravity Data", "Observation and base-station import.", 9000),
    FeatureDef("gravity.qc", "gravity", "Gravity QC", "Field, repeat, drift and reduction QC.", 17000),
    FeatureDef("gravity.processing", "gravity", "Gravity Reduction", "Free-air, Bouguer, grid and profile outputs.", 22000),
    FeatureDef("gravity.viewer", "gravity", "Gravity 2D/3D & Satellite", "Maps, profiles, spatial and terrain views.", 13000),
    FeatureDef("gravity.reports", "gravity", "Gravity Reports", "PDF/XLSX reports.", 8000),

    FeatureDef("vibroseis.data", "vibroseis", "Vibroseis Data", "VAPS and sweep/source design imports.", 9000),
    FeatureDef("vibroseis.qc", "vibroseis", "Vibroseis QC", "Sweep, force, phase, correlation and signal QC.", 18000),
    FeatureDef("vibroseis.viewer", "vibroseis", "Vibroseis Viewer", "Spatial and production visualization.", 10000),
    FeatureDef("vibroseis.planning", "vibroseis", "Vibroseis Planning", "Productivity, pilot export and planning tools.", 12000),

    FeatureDef("geodetic.data", "geodetic", "Geodetic Examiner", "DC/GNSS import and examiner.", 9000),
    FeatureDef("geodetic.qc", "geodetic", "Geodetic QC", "DOP, RMS, satellites, coordinate and vector QC.", 17000),
    FeatureDef("geodetic.coordinates", "geodetic", "Coordinates & Datum", "Coordinate, vector, CRS and equipment pages.", 12000),
    FeatureDef("geodetic.viewer", "geodetic", "Geodetic 2D/3D & Satellite", "Position and survey spatial views.", 10000),
    FeatureDef("geodetic.reports", "geodetic", "Geodetic Reports", "Reports and graph exports.", 8000),
)

FEATURE_BY_KEY = {feature.key: feature for feature in FEATURES}
MODULE_TITLES = {
    "seismic": "Seismic",
    "magnetic": "Magnetic",
    "electrical": "Electrical / IP-ERT",
    "gravity": "Gravity",
    "vibroseis": "Vibroseis",
    "geodetic": "Geodetic / GNSS",
}

FREE_FEATURES = ("seismic.viewer",)
ALL_FEATURE_KEYS = tuple(feature.key for feature in FEATURES)

PLANS: tuple[PlanDef, ...] = (
    PlanDef(
        "free",
        "Free Starter",
        "Login, project workspace, basic file handling and limited seismic viewing.",
        0,
        FREE_FEATURES,
    ),
    PlanDef(
        "modular",
        "Modular Professional",
        "Buy only the modules/submodules required for the current project.",
        0,
        (),
    ),
    PlanDef(
        "enterprise_all",
        "Enterprise All Modules",
        "All seismic, magnetic, electrical, gravity, vibroseis and geodetic modules.",
        175000,
        ALL_FEATURE_KEYS,
    ),
)
PLAN_BY_KEY = {plan.key: plan for plan in PLANS}

PROVIDER_FEATURE_MAP = {
    "segd": "seismic.segd",
    "segd_scanner": "seismic.scanner",
    "uphole": "seismic.uphole",
    "receiver_qc": "seismic.receiver",
    "smt": "seismic.receiver",
    "segy_viewer": "seismic.viewer",
    "converter": "seismic.converter",
    "visualization": "seismic.viewer",
    "magnetic_data": "magnetic.data",
    "magnetic_qc": "magnetic.qc",
    "magnetic_processing": "magnetic.processing",
    "magnetic_viewer": "magnetic.viewer",
    "magnetic_reports": "magnetic.reports",
    "electrical_data": "electrical.data",
    "electrical_qc": "electrical.qc",
    "electrical_processing": "electrical.processing",
    "electrical_viewer": "electrical.viewer",
    "electrical_reports": "electrical.reports",
    "gravity_data": "gravity.data",
    "gravity_qc": "gravity.qc",
    "gravity_processing": "gravity.processing",
    "gravity_viewer": "gravity.viewer",
    "gravity_reports": "gravity.reports",
    "vibroseis_data": "vibroseis.data",
    "vibroseis_qc": "vibroseis.qc",
    "vibroseis_viewer": "vibroseis.viewer",
    "vibroseis_planning": "vibroseis.planning",
    "geodetic_data": "geodetic.data",
    "geodetic_qc": "geodetic.qc",
    "geodetic_coordinates": "geodetic.coordinates",
    "geodetic_viewer": "geodetic.viewer",
    "geodetic_reports": "geodetic.reports",
}

ACTION_FEATURE_PREFIXES = (
    ("segd_scanner_", "seismic.scanner"),
    ("receiver_", "seismic.receiver"),
    ("smt_", "seismic.receiver"),
    ("uphole_", "seismic.uphole"),
    ("segd_", "seismic.segd"),
    ("segy_", "seismic.viewer"),
    ("visualization_", "seismic.viewer"),
    ("magnetic_", "magnetic.data"),
    ("gravity_", "gravity.data"),
    ("electrical_", "electrical.data"),
    ("vibroseis_", "vibroseis.data"),
    ("geodetic_", "geodetic.data"),
)

ACTION_FEATURE_OVERRIDES = {
    "segy_open_file": "seismic.viewer",
    "segy_open_2d3d": "seismic.viewer",
    "magnetic_open": "magnetic.data",
    "magnetic_open_rover": "magnetic.data",
    "magnetic_open_base": "magnetic.data",
    "magnetic_open_boundary": "magnetic.data",
    "magnetic_run_full": "magnetic.qc",
    "magnetic_run_raw": "magnetic.qc",
    "magnetic_run_processed": "magnetic.qc",
    "magnetic_despike": "magnetic.processing",
    "magnetic_diurnal": "magnetic.processing",
    "magnetic_level": "magnetic.processing",
    "magnetic_microlevel": "magnetic.processing",
    "magnetic_grid": "magnetic.processing",
    "magnetic_view_2d": "magnetic.viewer",
    "magnetic_view_3d": "magnetic.viewer",
    "magnetic_satellite": "magnetic.viewer",
    "magnetic_terrain": "magnetic.viewer",
    "magnetic_report_pdf": "magnetic.reports",
    "magnetic_report_xlsx": "magnetic.reports",
    "electrical_run_qc": "electrical.qc",
    "electrical_results": "electrical.qc",
    "electrical_thresholds": "electrical.qc",
    "electrical_sp_drift": "electrical.processing",
    "electrical_despike": "electrical.processing",
    "electrical_pseudosection": "electrical.processing",
    "electrical_view_2d": "electrical.viewer",
    "electrical_view_3d": "electrical.viewer",
    "electrical_satellite": "electrical.viewer",
    "electrical_terrain": "electrical.viewer",
    "gravity_run_full": "gravity.qc",
    "gravity_run_field": "gravity.qc",
    "gravity_run_final": "gravity.qc",
    "gravity_reduce": "gravity.processing",
    "gravity_grid": "gravity.processing",
    "gravity_view_2d": "gravity.viewer",
    "gravity_view_3d": "gravity.viewer",
    "gravity_satellite": "gravity.viewer",
    "gravity_report_pdf": "gravity.reports",
    "gravity_report_xlsx": "gravity.reports",
    "vibroseis_signal_qc": "vibroseis.qc",
    "vibroseis_vaps_qc": "vibroseis.qc",
    "vibroseis_correlation": "vibroseis.qc",
    "vibroseis_ground_force": "vibroseis.qc",
    "vibroseis_view_2d": "vibroseis.viewer",
    "vibroseis_view_3d": "vibroseis.viewer",
    "vibroseis_satellite": "vibroseis.viewer",
    "vibroseis_productivity": "vibroseis.planning",
    "vibroseis_export_pilot": "vibroseis.planning",
    "geodetic_run_qc": "geodetic.qc",
    "geodetic_qc_results": "geodetic.qc",
    "geodetic_graph_prev": "geodetic.qc",
    "geodetic_graph_next": "geodetic.qc",
    "geodetic_export_graphs": "geodetic.reports",
    "geodetic_positions": "geodetic.coordinates",
    "geodetic_vectors": "geodetic.coordinates",
    "geodetic_datum_crs": "geodetic.coordinates",
    "geodetic_equipment": "geodetic.coordinates",
    "geodetic_view_2d": "geodetic.viewer",
    "geodetic_view_3d": "geodetic.viewer",
    "geodetic_satellite": "geodetic.viewer",
    "geodetic_terrain": "geodetic.viewer",
    "geodetic_report_pdf": "geodetic.reports",
}

PUBLIC_ACTIONS = {
    "new_project", "open_project", "save_project", "import_file", "export_data",
    "project_properties", "refresh_project", "qc_history", "about", "preferences",
    "subscription_modules", "logout_account",
    "shortcuts", "documentation", "report_issue", "reset_layout", "toggle_explorer",
    "toggle_properties", "toggle_console", "save_layout", "load_layout",
}


def feature_for_provider(provider_id: str | None) -> str | None:
    provider = str(provider_id or "").strip()
    if provider in {"home", ""}:
        return None
    return PROVIDER_FEATURE_MAP.get(provider)


def feature_for_action(action_id: str | None) -> str | None:
    action = str(action_id or "").strip()
    if not action or action in PUBLIC_ACTIONS:
        return None
    if action in ACTION_FEATURE_OVERRIDES:
        return ACTION_FEATURE_OVERRIDES[action]
    for prefix, feature_key in ACTION_FEATURE_PREFIXES:
        if action.startswith(prefix):
            return feature_key
    return None


def module_for_feature(feature_key: str | None) -> str | None:
    if not feature_key:
        return None
    feature = FEATURE_BY_KEY.get(feature_key)
    return feature.module if feature else None


def features_for_plan(plan_key: str, selected_features: Iterable[str] | None = None) -> set[str]:
    plan = PLAN_BY_KEY.get(plan_key, PLAN_BY_KEY["free"])
    if plan.key == "modular":
        return {key for key in (selected_features or []) if key in FEATURE_BY_KEY}
    return set(plan.features)


def monthly_total_for_features(feature_keys: Iterable[str]) -> int:
    keys = {key for key in feature_keys if key in FEATURE_BY_KEY}
    return int(sum(FEATURE_BY_KEY[key].monthly_pkr for key in sorted(keys)))


def module_summary(feature_keys: Iterable[str]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {}
    for key in sorted(set(feature_keys)):
        feature = FEATURE_BY_KEY.get(key)
        if not feature:
            continue
        summary.setdefault(feature.module, []).append(feature.title)
    return summary
