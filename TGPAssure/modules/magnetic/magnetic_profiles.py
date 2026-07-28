from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.magnetic.constants import PROFILE_VERSION


_BASE_THRESHOLDS: dict[str, Any] = {
    "missing_value_max_pct": 1.0,
    "duplicate_record_max_pct": 0.2,
    "duplicate_timestamp_max_pct": 0.2,
    "timestamp_gap_max_s": 10.0,
    "timestamp_nonmonotonic_max_pct": 0.1,
    "base_rover_time_offset_max_s": 2.0,
    "coordinate_missing_max_pct": 0.5,
    "coordinate_jump_max_m": 100.0,
    "outside_boundary_max_pct": 0.5,
    "station_spacing_tolerance_pct": 35.0,
    "line_spacing_tolerance_pct": 25.0,
    "line_deviation_max_m": 20.0,
    "line_azimuth_tolerance_deg": 12.0,
    "ground_speed_max_m_s": 4.0,
    "gps_hdop_warn_max": 2.5,
    "gps_hdop_fail_max": 5.0,
    "gps_satellites_min": 5,
    "gps_fix_quality_min": 1.0,
    "gps_pps_missing_max_pct": 1.0,
    "sensor_validation_bad_max_pct": 0.1,
    "base_sampling_interval_max_s": 5.0,
    "base_gap_max_s": 30.0,
    "base_drift_max_nt": 100.0,
    "base_rate_max_nt_min": 5.0,
    "base_noise_rms_max_nt": 1.5,
    "diurnal_correction_max_nt": 100.0,
    "diurnal_residual_max_nt": 2.0,
    "spike_threshold_nt": 20.0,
    "spike_outlier_factor": 6.0,
    "dropout_max_pct": 0.2,
    "frozen_sequence_max_samples": 8,
    "sensor_disagreement_max_nt": 3.0,
    "sensor_range_min_nt": 15_000.0,
    "sensor_range_max_nt": 85_000.0,
    "noise_rms_max_nt": 2.5,
    "rolling_noise_max_nt": 4.0,
    "gradient_noise_max_nt_m": 2.0,
    "repeat_station_difference_max_nt": 5.0,
    "repeat_station_rms_max_nt": 3.0,
    "tie_misclosure_max_nt": 10.0,
    "tie_misclosure_rms_max_nt": 5.0,
    "altitude_deviation_max_m": 15.0,
    "terrain_clearance_min_m": 30.0,
    "heading_deviation_max_deg": 12.0,
    "lag_max_s": 2.0,
    "cultural_noise_outlier_factor": 8.0,
    "leveling_residual_max_nt": 5.0,
    "line_bias_max_nt": 8.0,
    "microlevel_correction_max_nt": 10.0,
    "grid_void_max_pct": 5.0,
    "grid_extrapolation_max_pct": 10.0,
    "grid_edge_artifact_max_pct": 5.0,
    "grid_min_points_per_cell": 1,
    "nominal_station_spacing_m": 25.0,
    "nominal_line_spacing_m": 100.0,
    "nominal_tie_spacing_m": 1000.0,
    "expected_traverse_azimuth_deg": None,
    "expected_tie_azimuth_deg": None,
}

MAGNETIC_THRESHOLD_LABELS: dict[str, str] = {
    "missing_value_max_pct": "Maximum missing values (%)",
    "duplicate_record_max_pct": "Maximum duplicate records (%)",
    "duplicate_timestamp_max_pct": "Maximum duplicate timestamps (%)",
    "timestamp_gap_max_s": "Maximum timestamp gap (s)",
    "timestamp_nonmonotonic_max_pct": "Maximum non-monotonic timestamps (%)",
    "base_rover_time_offset_max_s": "Maximum rover/base clock offset (s)",
    "coordinate_missing_max_pct": "Maximum missing coordinates (%)",
    "coordinate_jump_max_m": "Maximum coordinate jump (m)",
    "outside_boundary_max_pct": "Maximum stations outside boundary (%)",
    "station_spacing_tolerance_pct": "Station-spacing tolerance (%)",
    "line_spacing_tolerance_pct": "Line-spacing tolerance (%)",
    "line_deviation_max_m": "Maximum line straightness deviation (m)",
    "line_azimuth_tolerance_deg": "Line azimuth tolerance (degrees)",
    "ground_speed_max_m_s": "Maximum ground survey speed (m/s)",
    "gps_hdop_warn_max": "GPS HDOP warning threshold",
    "gps_hdop_fail_max": "GPS HDOP failure threshold",
    "gps_satellites_min": "Minimum GPS satellites",
    "gps_fix_quality_min": "Minimum GPS fix quality",
    "gps_pps_missing_max_pct": "Maximum GPS PPS-missing records (%)",
    "sensor_validation_bad_max_pct": "Maximum sensor validation failures (%)",
    "base_sampling_interval_max_s": "Maximum base sampling interval (s)",
    "base_gap_max_s": "Maximum base-station gap (s)",
    "base_drift_max_nt": "Maximum base-station drift (nT)",
    "base_rate_max_nt_min": "Maximum base field rate (nT/min)",
    "base_noise_rms_max_nt": "Maximum base noise RMS (nT)",
    "diurnal_correction_max_nt": "Maximum diurnal correction magnitude (nT)",
    "diurnal_residual_max_nt": "Maximum residual diurnal trend (nT)",
    "spike_threshold_nt": "Absolute spike threshold (nT)",
    "spike_outlier_factor": "Robust spike outlier factor",
    "dropout_max_pct": "Maximum dropouts (%)",
    "frozen_sequence_max_samples": "Maximum repeated-value sequence (samples)",
    "sensor_disagreement_max_nt": "Maximum dual-sensor disagreement (nT)",
    "sensor_range_min_nt": "Minimum valid total field (nT)",
    "sensor_range_max_nt": "Maximum valid total field (nT)",
    "noise_rms_max_nt": "Maximum line noise RMS (nT)",
    "rolling_noise_max_nt": "Maximum rolling noise (nT)",
    "gradient_noise_max_nt_m": "Maximum gradient noise (nT/m)",
    "repeat_station_difference_max_nt": "Maximum repeat-station difference (nT)",
    "repeat_station_rms_max_nt": "Maximum repeat-station RMS (nT)",
    "tie_misclosure_max_nt": "Maximum tie intersection misclosure (nT)",
    "tie_misclosure_rms_max_nt": "Maximum tie misclosure RMS (nT)",
    "altitude_deviation_max_m": "Maximum altitude deviation (m)",
    "terrain_clearance_min_m": "Minimum terrain clearance (m)",
    "heading_deviation_max_deg": "Maximum heading deviation (degrees)",
    "lag_max_s": "Maximum sensor lag (s)",
    "cultural_noise_outlier_factor": "Cultural-noise outlier factor",
    "leveling_residual_max_nt": "Maximum residual leveling error (nT)",
    "line_bias_max_nt": "Maximum line bias (nT)",
    "microlevel_correction_max_nt": "Maximum microlevel correction (nT)",
    "grid_void_max_pct": "Maximum grid void area (%)",
    "grid_extrapolation_max_pct": "Maximum grid extrapolation (%)",
    "grid_edge_artifact_max_pct": "Maximum grid edge artifacts (%)",
    "grid_min_points_per_cell": "Minimum points per grid cell",
    "nominal_station_spacing_m": "Nominal station spacing (m)",
    "nominal_line_spacing_m": "Nominal traverse spacing (m)",
    "nominal_tie_spacing_m": "Nominal tie-line spacing (m)",
    "expected_traverse_azimuth_deg": "Expected traverse azimuth (degrees)",
    "expected_tie_azimuth_deg": "Expected tie-line azimuth (degrees)",
}


@dataclass(frozen=True)
class MagneticProfile:
    name: str
    display_name: str
    version: str
    thresholds: dict[str, Any]


def _scaled(**overrides: Any) -> dict[str, Any]:
    values = dict(_BASE_THRESHOLDS)
    values.update(overrides)
    return values


PROFILES: dict[str, MagneticProfile] = {
    "field": MagneticProfile(
        "field", "Field QC", PROFILE_VERSION,
        _scaled(
            missing_value_max_pct=3.0, timestamp_gap_max_s=30.0,
            coordinate_jump_max_m=200.0, outside_boundary_max_pct=2.0,
            gps_hdop_warn_max=4.0, gps_hdop_fail_max=8.0, gps_satellites_min=4,
            gps_pps_missing_max_pct=5.0, sensor_validation_bad_max_pct=1.0,
            base_gap_max_s=90.0, base_drift_max_nt=150.0,
            base_rate_max_nt_min=8.0, base_noise_rms_max_nt=3.0,
            spike_threshold_nt=35.0, noise_rms_max_nt=5.0,
            repeat_station_difference_max_nt=8.0, tie_misclosure_max_nt=15.0,
            leveling_residual_max_nt=8.0, grid_void_max_pct=10.0,
        ),
    ),
    "standard": MagneticProfile("standard", "Standard QC", PROFILE_VERSION, _scaled()),
    "processing": MagneticProfile(
        "processing", "Processing QC", PROFILE_VERSION,
        _scaled(
            missing_value_max_pct=0.5, base_gap_max_s=20.0,
            gps_hdop_warn_max=2.0, gps_hdop_fail_max=4.0, gps_satellites_min=6,
            gps_pps_missing_max_pct=0.5, sensor_validation_bad_max_pct=0.05,
            base_noise_rms_max_nt=1.0, diurnal_residual_max_nt=1.0,
            noise_rms_max_nt=2.0, tie_misclosure_max_nt=7.0,
            tie_misclosure_rms_max_nt=3.5, leveling_residual_max_nt=3.0,
            line_bias_max_nt=5.0, grid_void_max_pct=3.0,
            grid_edge_artifact_max_pct=3.0,
        ),
    ),
    "strict": MagneticProfile(
        "strict", "Strict Final QC", PROFILE_VERSION,
        _scaled(
            missing_value_max_pct=0.1, duplicate_record_max_pct=0.05,
            duplicate_timestamp_max_pct=0.05, timestamp_gap_max_s=5.0,
            coordinate_missing_max_pct=0.1, coordinate_jump_max_m=50.0,
            gps_hdop_warn_max=1.5, gps_hdop_fail_max=3.0, gps_satellites_min=7,
            gps_pps_missing_max_pct=0.1, sensor_validation_bad_max_pct=0.01,
            outside_boundary_max_pct=0.1, station_spacing_tolerance_pct=20.0,
            line_deviation_max_m=10.0, line_azimuth_tolerance_deg=7.0,
            base_sampling_interval_max_s=2.0, base_gap_max_s=10.0,
            base_drift_max_nt=75.0, base_rate_max_nt_min=3.0,
            base_noise_rms_max_nt=0.75, diurnal_correction_max_nt=75.0,
            diurnal_residual_max_nt=0.75, spike_threshold_nt=12.0,
            spike_outlier_factor=5.0, dropout_max_pct=0.05,
            sensor_disagreement_max_nt=1.5, noise_rms_max_nt=1.5,
            repeat_station_difference_max_nt=3.0, repeat_station_rms_max_nt=2.0,
            tie_misclosure_max_nt=5.0, tie_misclosure_rms_max_nt=2.5,
            leveling_residual_max_nt=2.0, line_bias_max_nt=3.0,
            microlevel_correction_max_nt=5.0, grid_void_max_pct=1.0,
            grid_extrapolation_max_pct=3.0, grid_edge_artifact_max_pct=2.0,
        ),
    ),
}


def get_profile(name: str = "standard", overrides: dict[str, Any] | None = None) -> MagneticProfile:
    key = name.strip().lower()
    if key not in PROFILES:
        raise KeyError(f"Unknown magnetic QC profile '{name}'")
    profile = PROFILES[key]
    thresholds = dict(profile.thresholds)
    thresholds.update(overrides or {})
    return MagneticProfile(profile.name, profile.display_name, profile.version, thresholds)
