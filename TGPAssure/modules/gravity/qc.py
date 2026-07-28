from __future__ import annotations

from math import pi, sin
from typing import Any


class TidalCorrectionQC:
    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        corrected = [{**row, 'tidal_corrected_gravity_mgal': float(row['observed_gravity_mgal']) - float(row.get('tidal_correction_mgal', 0.0))} for row in records]
        return {'records': corrected, 'passed': True}


class FreeAirCorrectionQC:
    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        corrected = [{**row, 'free_air_correction_mgal': 0.3086 * row['elevation_m'], 'free_air_anomaly_mgal': row.get('tidal_corrected_gravity_mgal', row['observed_gravity_mgal']) - 0.3086 * row['elevation_m']} for row in records]
        return {'records': corrected, 'passed': all(abs(row['free_air_correction_mgal']) < 10000 for row in corrected)}


class BouguerCorrectionQC:
    def __init__(self, density_g_cm3: float = 2.67) -> None:
        self.density_g_cm3 = float(density_g_cm3)

    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        corrected = []
        for row in records:
            latitude = row['latitude'] * pi / 180.0
            normal_gravity = 978032.67715 * (1 + 0.0053024 * sin(latitude) ** 2 - 0.0000058 * sin(2 * latitude) ** 2)
            slab = 0.04193 * self.density_g_cm3 * row['elevation_m']
            gravity = row.get('tidal_corrected_gravity_mgal', row['observed_gravity_mgal'])
            corrected.append({**row, 'normal_gravity_mgal': normal_gravity, 'bouguer_correction_mgal': slab, 'bouguer_anomaly_mgal': gravity - normal_gravity + 0.3086 * row['elevation_m'] - slab})
        return {'records': corrected, 'density_g_cm3': self.density_g_cm3, 'passed': True}
