from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "datetime", "date_time", "time_stamp", "utc_time", "gps_time"),
    "date": ("date", "survey_date", "utc_date"),
    "time": ("time", "survey_time", "utc", "hhmmss"),
    "x": ("x", "easting", "east", "utm_e", "longitude", "longitude_deg", "lon", "lon_deg", "long", "gps_longitude"),
    "y": ("y", "northing", "north", "utm_n", "latitude", "latitude_deg", "lat", "lat_deg", "gps_latitude"),
    "elevation": ("elevation", "altitude", "alt_m", "height", "z", "gps_height", "rl"),
    "total_field": ("total_field", "total_field_nt", "mag", "mag_nt", "magnetic_field", "field", "field_nt", "tf", "tmi", "total_intensity", "nt"),
    "base_field": ("base_field", "base_mag", "base", "base_total_field", "base_tmi"),
    "sensor_1": ("sensor_1", "sensor1", "mag1", "top_sensor", "upper_sensor"),
    "sensor_2": ("sensor_2", "sensor2", "mag2", "bottom_sensor", "lower_sensor"),
    "line_id": ("line", "line_id", "line_no", "line_number", "flight_line", "traverse"),
    "station_id": ("station", "station_id", "station_no", "point", "fid", "record"),
    "line_type": ("line_type", "type", "survey_line_type"),
    "temperature": ("temperature", "temp", "sensor_temp", "instrument_temperature"),
    "gps_quality": ("gps_quality", "fix_quality", "quality", "gps_fix"),
    "gps_hdop": ("gps_hdop", "hdop"),
    "gps_pps_valid": ("gps_pps_valid", "pps", "pps_valid"),
    "satellites": ("satellites", "sats", "sat_count", "sv", "number_satellites"),
    "heading": ("heading", "heading_deg", "azimuth", "course", "bearing"),
    "speed": ("speed", "ground_speed", "velocity"),
    "terrain_clearance": ("terrain_clearance", "clearance", "sensor_clearance"),
    "roll": ("roll",),
    "pitch": ("pitch",),
    "yaw": ("yaw",),
}


def normalise_header(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^]]*]", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


@dataclass(frozen=True)
class MappingCandidate:
    canonical_name: str
    source_name: str
    confidence: float


class MagneticColumnMapper:
    def detect(self, headers: Iterable[str]) -> dict[str, str]:
        original = list(headers)
        normalised = {normalise_header(name): name for name in original}
        result: dict[str, str] = {}
        for canonical, aliases in ALIASES.items():
            if canonical in normalised:
                result[canonical] = normalised[canonical]
                continue
            matches = [normalised[alias] for alias in aliases if alias in normalised]
            if matches:
                result[canonical] = matches[0]
                continue
            for key, source in normalised.items():
                if any(key.startswith(alias + "_") or key.endswith("_" + alias) for alias in aliases):
                    result[canonical] = source
                    break
        return result

    def merge(self, detected: dict[str, str], explicit: dict[str, str]) -> dict[str, str]:
        merged = dict(detected)
        for canonical, source in explicit.items():
            if source:
                merged[canonical] = source
        return merged
