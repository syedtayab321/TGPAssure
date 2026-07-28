from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from modules.gravity.constants import (
    BOUGUER_CORRECTION,
    COMPLETE_BOUGUER_ANOMALY,
    DEFAULT_DENSITY_G_CM3,
    DRIFT_CORRECTION,
    FREE_AIR_ANOMALY,
    FREE_AIR_CORRECTION,
    NORMAL_GRAVITY,
    RAW_GRAVITY,
    SIMPLE_BOUGUER_ANOMALY,
    TERRAIN_CORRECTION,
    TIDE_CORRECTION,
    TIDE_DRIFT_CORRECTED,
)
from modules.gravity.models import GravityDataset


class GravityProcessingError(RuntimeError):
    pass


class GravityProcessingEngine:
    @staticmethod
    def normal_gravity_1980(latitude_deg: np.ndarray) -> np.ndarray:
        """IGF-1980 normal gravity in mGal."""
        lat = np.deg2rad(np.asarray(latitude_deg, dtype=float))
        sin2 = np.sin(lat) ** 2
        return 978032.67715 * (1.0 + 0.0053024 * sin2 - 0.0000058 * np.sin(2.0 * lat) ** 2)

    @staticmethod
    def _time_seconds(timestamps: np.ndarray) -> np.ndarray:
        values = np.asarray(timestamps, dtype="datetime64[ms]").astype("int64").astype(float) / 1000.0
        if values.size:
            values -= values[0]
        return values

    def calculate_base_drift(self, observations: GravityDataset, base: GravityDataset | None) -> np.ndarray:
        if base is None or RAW_GRAVITY not in base.channels or base.record_count < 2:
            return np.zeros(observations.record_count, dtype=float)
        obs_t = self._time_seconds(observations.timestamps)
        base_abs = np.asarray(base.timestamps, dtype="datetime64[ms]").astype("int64").astype(float) / 1000.0
        obs_abs = np.asarray(observations.timestamps, dtype="datetime64[ms]").astype("int64").astype(float) / 1000.0
        base_g = base.channel(RAW_GRAVITY)
        valid = np.isfinite(base_abs) & np.isfinite(base_g)
        if np.count_nonzero(valid) < 2:
            return np.zeros(observations.record_count, dtype=float)
        order = np.argsort(base_abs[valid])
        bt = base_abs[valid][order]
        bg = base_g[valid][order]
        reference = float(np.nanmedian(bg[: max(1, min(3, bg.size))]))
        drift_samples = bg - reference
        drift = np.interp(obs_abs, bt, drift_samples, left=drift_samples[0], right=drift_samples[-1])
        return np.asarray(drift, dtype=float)

    def run_standard_reduction(
        self,
        observations: GravityDataset,
        *,
        base: GravityDataset | None = None,
        density_g_cm3: float = DEFAULT_DENSITY_G_CM3,
    ) -> GravityDataset:
        if RAW_GRAVITY not in observations.channels:
            raise GravityProcessingError(f"Required raw channel '{RAW_GRAVITY}' is missing")
        raw = observations.channel(RAW_GRAVITY).copy()
        tide = observations.channels.get(TIDE_CORRECTION, np.zeros(observations.record_count, dtype=float))
        terrain = observations.channels.get(TERRAIN_CORRECTION, np.zeros(observations.record_count, dtype=float))
        elevation = np.asarray(observations.elevation, dtype=float)
        latitude = np.asarray(observations.latitude, dtype=float)
        if not np.any(np.isfinite(latitude)):
            raise GravityProcessingError("Latitude is required for normal-gravity reduction")
        if not np.any(np.isfinite(elevation)):
            raise GravityProcessingError("Elevation is required for free-air and Bouguer reduction")

        drift = self.calculate_base_drift(observations, base)
        corrected = raw - np.nan_to_num(tide, nan=0.0) - np.nan_to_num(drift, nan=0.0)
        normal = self.normal_gravity_1980(latitude)
        free_air_corr = 0.3086 * elevation
        bouguer_corr = 0.04193 * float(density_g_cm3) * elevation
        free_air_anomaly = corrected - normal + free_air_corr
        simple = free_air_anomaly - bouguer_corr
        complete = simple + np.nan_to_num(terrain, nan=0.0)

        derived = (
            (DRIFT_CORRECTION, drift, RAW_GRAVITY, "base_drift_interpolation", {}),
            (TIDE_DRIFT_CORRECTED, corrected, RAW_GRAVITY, "tide_and_drift_correction", {}),
            (NORMAL_GRAVITY, normal, None, "igf_1980_normal_gravity", {}),
            (FREE_AIR_CORRECTION, free_air_corr, None, "free_air_correction", {"coefficient_mgal_per_m": 0.3086}),
            (FREE_AIR_ANOMALY, free_air_anomaly, TIDE_DRIFT_CORRECTED, "free_air_anomaly", {}),
            (BOUGUER_CORRECTION, bouguer_corr, None, "infinite_slab_bouguer_correction", {"density_g_cm3": density_g_cm3}),
            (SIMPLE_BOUGUER_ANOMALY, simple, FREE_AIR_ANOMALY, "simple_bouguer_anomaly", {"density_g_cm3": density_g_cm3}),
            (COMPLETE_BOUGUER_ANOMALY, complete, SIMPLE_BOUGUER_ANOMALY, "terrain_corrected_bouguer_anomaly", {"density_g_cm3": density_g_cm3}),
        )
        for name, values, parent, operation, params in derived:
            observations.add_derived_channel(
                name, values, parent_channel=parent, operation=operation, parameters=params,
                overwrite=name in observations.channels,
            )
        # Raw values must remain byte-for-byte equivalent numerically.
        observations.channels[RAW_GRAVITY] = raw
        return observations

    @staticmethod
    def _local_xy(dataset: GravityDataset) -> tuple[np.ndarray, np.ndarray]:
        projected = np.isfinite(dataset.x) & np.isfinite(dataset.y)
        if np.count_nonzero(projected) >= 3:
            return dataset.x.copy(), dataset.y.copy()
        if np.count_nonzero(np.isfinite(dataset.longitude) & np.isfinite(dataset.latitude)) < 3:
            raise GravityProcessingError("At least three valid coordinate pairs are required")
        lon = dataset.longitude.astype(float)
        lat = dataset.latitude.astype(float)
        lon0 = float(np.nanmedian(lon))
        lat0 = float(np.nanmedian(lat))
        x = (lon - lon0) * 111_320.0 * np.cos(np.deg2rad(lat0))
        y = (lat - lat0) * 110_540.0
        return x, y

    def grid(
        self,
        dataset: GravityDataset,
        *,
        source_channel: str = COMPLETE_BOUGUER_ANOMALY,
        cell_size: float | None = None,
        method: str = "linear",
    ) -> dict[str, Any]:
        if source_channel not in dataset.channels:
            raise GravityProcessingError(f"Run standard reduction before gridding; '{source_channel}' is unavailable")
        x, y = self._local_xy(dataset)
        z = dataset.channel(source_channel)
        valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        if np.count_nonzero(valid) < 3:
            raise GravityProcessingError("At least three valid reduced gravity observations are required")
        x, y, z = x[valid], y[valid], z[valid]
        if cell_size is None:
            if x.size > 1:
                steps = np.hypot(np.diff(x), np.diff(y))
                steps = steps[steps > 0]
                cell_size = float(np.nanmedian(steps)) if steps.size else 50.0
            else:
                cell_size = 50.0
        cell_size = max(float(cell_size), 0.01)
        gx = np.arange(float(np.min(x)), float(np.max(x)) + cell_size, cell_size)
        gy = np.arange(float(np.min(y)), float(np.max(y)) + cell_size, cell_size)
        xx, yy = np.meshgrid(gx, gy)
        try:
            from scipy.interpolate import griddata
            selected = method if method in {"linear", "nearest", "cubic"} else "linear"
            values = griddata(np.column_stack((x, y)), z, (xx, yy), method=selected)
            if selected != "nearest" and np.any(~np.isfinite(values)):
                nearest = griddata(np.column_stack((x, y)), z, (xx, yy), method="nearest")
                values[~np.isfinite(values)] = nearest[~np.isfinite(values)]
        except Exception:
            values = self._idw(x, y, z, xx, yy)
        return {
            "values": values,
            "x": gx,
            "y": gy,
            "cell_size": cell_size,
            "source_channel": source_channel,
            "method": method,
            "crs": dataset.crs,
        }

    @staticmethod
    def _idw(x: np.ndarray, y: np.ndarray, z: np.ndarray, xx: np.ndarray, yy: np.ndarray, power: float = 2.0) -> np.ndarray:
        out = np.empty_like(xx, dtype=float)
        for r in range(xx.shape[0]):
            dx = xx[r, :, None] - x[None, :]
            dy = yy[r, :, None] - y[None, :]
            d2 = dx * dx + dy * dy
            weights = 1.0 / np.maximum(d2, 1e-12) ** (power / 2.0)
            vals = np.sum(weights * z[None, :], axis=1) / np.sum(weights, axis=1)
            exact = d2 == 0
            for c in np.flatnonzero(np.any(exact, axis=1)):
                vals[c] = z[np.flatnonzero(exact[c])[0]]
            out[r] = vals
        return out

    def export_csv(self, dataset: GravityDataset, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        channels = list(dataset.channel_names)
        with output.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([
                "timestamp", "station_id", "line_id", "latitude", "longitude", "x", "y", "elevation_m", *channels
            ])
            for i in range(dataset.record_count):
                writer.writerow([
                    str(dataset.timestamps[i]), dataset.station_id[i], dataset.line_id[i], dataset.latitude[i],
                    dataset.longitude[i], dataset.x[i], dataset.y[i], dataset.elevation[i],
                    *[dataset.channels[name][i] for name in channels],
                ])
        return output
