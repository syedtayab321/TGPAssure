from __future__ import annotations

from enum import Enum


class ElectricalMethod(str, Enum):
    AUTO = "auto"
    ERT = "ert"
    VES = "ves"
    PROFILING = "profiling"
    TDIP = "tdip"
    FDIP = "fdip"
    SIP = "sip"
    SP = "sp"
    MALM = "malm"
    EQUIPOTENTIAL = "equipotential"
    TELLURIC = "telluric"


METHOD_LABELS: dict[ElectricalMethod, str] = {
    ElectricalMethod.AUTO: "Auto Detect",
    ElectricalMethod.ERT: "Electrical Resistivity Tomography (ERT)",
    ElectricalMethod.VES: "Vertical Electrical Sounding (VES)",
    ElectricalMethod.PROFILING: "DC Resistivity Profiling",
    ElectricalMethod.TDIP: "Time-Domain Induced Polarization (TDIP)",
    ElectricalMethod.FDIP: "Frequency-Domain Induced Polarization (FDIP)",
    ElectricalMethod.SIP: "Spectral IP / Complex Resistivity (SIP)",
    ElectricalMethod.SP: "Self-Potential (SP)",
    ElectricalMethod.MALM: "Mise-à-la-Masse (MALM)",
    ElectricalMethod.EQUIPOTENTIAL: "Equipotential / Potential Mapping",
    ElectricalMethod.TELLURIC: "Telluric Electric-Field Method",
}


SUPPORTED_EXTENSIONS = {".csv", ".txt", ".dat", ".xyz", ".tsv", ".xlsx", ".xlsm"}


# These defaults are intentionally conservative QC starting points, not universal
# acceptance criteria. They remain editable in the dashboard/profile before a run.
DEFAULT_QC_THRESHOLDS: dict[str, float] = {
    "contact_resistance_warn_ohm": 20_000.0,
    "stack_std_warn_pct": 5.0,
    "reciprocal_warn_pct": 5.0,
    "reciprocal_fail_pct": 10.0,
    "min_current_ma": 0.01,
    "min_abs_voltage_mv": 0.001,
    "repeat_warn_pct": 10.0,
    "outlier_mad_z": 6.0,
    "sp_drift_warn_mv": 5.0,
    "sp_repeat_warn_mv": 5.0,
    "tdip_negative_warn_mv_v": 0.0,
    "tdip_extreme_warn_mv_v": 1000.0,
    "sip_abs_phase_warn_mrad": 1600.0,
}


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "line_id": ("line", "line_id", "lineno", "line_no", "profile", "traverse"),
    "array_type": ("array_type", "array", "electrode_array", "configuration", "array_name"),
    "station": ("station", "station_id", "station_no", "chainage", "distance", "position", "x"),
    "easting": ("easting", "east", "utm_e", "x_coord", "x_coordinate", "longitude", "lon"),
    "northing": ("northing", "north", "utm_n", "y_coord", "y_coordinate", "latitude", "lat"),
    "elevation": ("elevation", "elev", "z", "altitude", "height"),
    "a": ("a", "c1", "tx1", "current_a", "electrode_a", "a_pos", "a_position"),
    "b": ("b", "c2", "tx2", "current_b", "electrode_b", "b_pos", "b_position"),
    "m": ("m", "p1", "rx1", "potential_m", "electrode_m", "m_pos", "m_position"),
    "n": ("n", "p2", "rx2", "potential_n", "electrode_n", "n_pos", "n_position"),
    "ab2_m": ("ab/2", "ab2", "ab_2", "half_ab", "ab2_m"),
    "mn2_m": ("mn/2", "mn2", "mn_2", "half_mn", "mn2_m"),
    "current_ma": ("current", "current_ma", "i", "in", "iab", "i_ma", "tx_current", "injected_current", "output_current"),
    "voltage_mv": ("voltage", "voltage_mv", "v", "vp", "vmn", "v_mv", "rx_voltage", "primary_voltage", "potential_mv", "potential"),
    "electric_field_mv_km": ("electric_field", "electric_field_mv_km", "efield", "e_field", "mv_km", "field_mv_km"),
    "electric_field_x_mv_km": ("electric_field_x", "electric_field_x_mv_km", "ex", "ex_mv_km"),
    "electric_field_y_mv_km": ("electric_field_y", "electric_field_y_mv_km", "ey", "ey_mv_km"),
    "resistance_ohm": ("resistance", "resistance_ohm", "r", "r_ohm", "apparent_resistance"),
    "apparent_resistivity_ohm_m": (
        "apparent_resistivity", "resistivity", "rho", "rhoa", "rho_a", "app_res", "app_resistivity",
        "apparent_resistivity_ohm_m", "res_ohmm", "ohm_m",
    ),
    "contact_resistance_ohm": (
        "contact_resistance", "contact_resistance_ohm", "ground_resistance", "rab", "contact_r", "rs_check",
    ),
    "stack_std_pct": ("stack_std", "std", "std_pct", "stack_error", "stacking_error", "q", "q_pct", "dev", "dev_pct", "deviation_pct"),
    "chargeability_mv_v": (
        "chargeability", "ip", "ip_mv_v", "chargeability_mv_v", "apparent_chargeability", "ma",
    ),
    "sp_mv": ("sp", "sp_mv", "self_potential", "self_potential_mv", "spontaneous_potential", "natural_potential"),
    "frequency_hz": ("frequency", "freq", "frequency_hz", "freq_hz", "hz"),
    "phase_mrad": ("phase", "phase_mrad", "phase_shift", "phi", "phase_milliradian", "mrad"),
    "phase_deg": ("phase_deg", "phase_degrees", "phase_degree"),
    "amplitude": ("amplitude", "magnitude", "impedance_magnitude", "resistivity_magnitude"),
    "timestamp": ("timestamp", "datetime", "date_time", "time", "acquisition_time"),
    "is_base": ("is_base", "base", "base_station", "reference", "is_reference"),
    "source_id": ("source_id", "source", "energized_body", "source_electrode", "source_station"),
    "repeat_id": ("repeat_id", "repeat", "reading_id", "measurement_id", "mem", "memory"),
}


METHOD_REQUIRED_FIELDS: dict[ElectricalMethod, tuple[tuple[str, ...], ...]] = {
    ElectricalMethod.ERT: (("apparent_resistivity_ohm_m", "resistance_ohm", "voltage_mv"), ("a",), ("b",), ("m",), ("n",)),
    ElectricalMethod.VES: (("apparent_resistivity_ohm_m", "resistance_ohm", "voltage_mv"), ("ab2_m", "a")),
    ElectricalMethod.PROFILING: (("apparent_resistivity_ohm_m", "resistance_ohm", "voltage_mv"),),
    ElectricalMethod.TDIP: (("chargeability_mv_v",),),
    ElectricalMethod.FDIP: (("frequency_hz",), ("phase_mrad", "phase_deg", "chargeability_mv_v")),
    ElectricalMethod.SIP: (("frequency_hz",), ("phase_mrad", "phase_deg")),
    ElectricalMethod.SP: (("sp_mv", "voltage_mv"),),
    ElectricalMethod.MALM: (("voltage_mv", "sp_mv"), ("source_id", "a")),
    ElectricalMethod.EQUIPOTENTIAL: (("voltage_mv", "sp_mv"),),
    ElectricalMethod.TELLURIC: (("electric_field_mv_km", "electric_field_x_mv_km", "electric_field_y_mv_km", "voltage_mv", "sp_mv"),),
}
