from __future__ import annotations

from copy import deepcopy

_PROFILES: dict[str, dict[str, float]] = {
    "field": {
        "timestamp_gap_warn_min": 60.0,
        "elevation_jump_warn_m": 30.0,
        "gravity_spike_warn_mgal": 1.0,
        "base_drift_warn_mgal_hr": 0.20,
        "repeat_rms_warn_mgal": 0.20,
        "loop_closure_warn_mgal": 0.30,
        "crossover_warn_mgal": 0.30,
        "anomaly_mad_z_warn": 8.0,
    },
    "standard": {
        "timestamp_gap_warn_min": 30.0,
        "elevation_jump_warn_m": 15.0,
        "gravity_spike_warn_mgal": 0.50,
        "base_drift_warn_mgal_hr": 0.10,
        "repeat_rms_warn_mgal": 0.10,
        "loop_closure_warn_mgal": 0.15,
        "crossover_warn_mgal": 0.15,
        "anomaly_mad_z_warn": 6.0,
    },
    "strict": {
        "timestamp_gap_warn_min": 15.0,
        "elevation_jump_warn_m": 8.0,
        "gravity_spike_warn_mgal": 0.25,
        "base_drift_warn_mgal_hr": 0.05,
        "repeat_rms_warn_mgal": 0.05,
        "loop_closure_warn_mgal": 0.08,
        "crossover_warn_mgal": 0.08,
        "anomaly_mad_z_warn": 4.5,
    },
}


def get_profile(name: str = "standard", overrides: dict[str, float] | None = None) -> dict[str, float]:
    key = str(name or "standard").strip().lower()
    if key not in _PROFILES:
        raise ValueError(f"Unknown gravity QC profile: {name}")
    profile = deepcopy(_PROFILES[key])
    if overrides:
        profile.update({str(k): float(v) for k, v in overrides.items()})
    return profile


def profile_names() -> tuple[str, ...]:
    return tuple(_PROFILES)
