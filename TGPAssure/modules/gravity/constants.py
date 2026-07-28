from __future__ import annotations

RAW_GRAVITY = "observed_gravity_mgal"
TIDE_CORRECTION = "tide_correction_mgal"
DRIFT_CORRECTION = "drift_correction_mgal"
TIDE_DRIFT_CORRECTED = "tide_drift_corrected_gravity_mgal"
NORMAL_GRAVITY = "normal_gravity_mgal"
FREE_AIR_CORRECTION = "free_air_correction_mgal"
FREE_AIR_ANOMALY = "free_air_anomaly_mgal"
BOUGUER_CORRECTION = "bouguer_correction_mgal"
TERRAIN_CORRECTION = "terrain_correction_mgal"
SIMPLE_BOUGUER_ANOMALY = "simple_bouguer_anomaly_mgal"
COMPLETE_BOUGUER_ANOMALY = "complete_bouguer_anomaly_mgal"

GRAVITY_CHANNELS = (
    RAW_GRAVITY,
    TIDE_CORRECTION,
    DRIFT_CORRECTION,
    TIDE_DRIFT_CORRECTED,
    NORMAL_GRAVITY,
    FREE_AIR_CORRECTION,
    FREE_AIR_ANOMALY,
    BOUGUER_CORRECTION,
    TERRAIN_CORRECTION,
    SIMPLE_BOUGUER_ANOMALY,
    COMPLETE_BOUGUER_ANOMALY,
)

DEFAULT_DENSITY_G_CM3 = 2.67
SUPPORTED_EXTENSIONS = {".csv", ".txt", ".dat", ".xyz", ".xlsx", ".xlsm"}
