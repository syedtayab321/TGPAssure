from __future__ import annotations

"""Coordinate normalization helpers for geophysical map overlays.

The application deliberately avoids guessing arbitrary projected CRSs.  WGS84
latitude/longitude and WGS84 UTM zones (EPSG:326xx/327xx) are handled directly;
other projected systems must be supplied in geographic coordinates before a
Google basemap overlay is rendered.
"""

from dataclasses import dataclass
import re
from typing import Iterable

import numpy as np


class CoordinateTransformError(ValueError):
    """Raised when coordinates cannot be transformed safely to WGS84."""


@dataclass(frozen=True)
class GeographicCoordinates:
    longitude: np.ndarray
    latitude: np.ndarray
    altitude_m: np.ndarray
    source_crs: str

    @property
    def valid_mask(self) -> np.ndarray:
        return (
            np.isfinite(self.longitude)
            & np.isfinite(self.latitude)
            & (self.longitude >= -180.0)
            & (self.longitude <= 180.0)
            & (self.latitude >= -90.0)
            & (self.latitude <= 90.0)
        )


def _as_float(values: Iterable[float] | np.ndarray | None, length: int | None = None) -> np.ndarray:
    if values is None:
        return np.full(int(length or 0), np.nan, dtype=float)
    arr = np.asarray(values, dtype=float).reshape(-1)
    if length is not None and arr.size != int(length):
        raise CoordinateTransformError(f"Coordinate array has {arr.size} values; expected {length}.")
    return arr


def normalize_crs(crs: str | None) -> str:
    text = str(crs or "").strip().upper().replace(" ", "")
    aliases = {
        "WGS84": "EPSG:4326",
        "WGS1984": "EPSG:4326",
        "4326": "EPSG:4326",
    }
    return aliases.get(text, text)


def to_wgs84(
    x: Iterable[float] | np.ndarray | None = None,
    y: Iterable[float] | np.ndarray | None = None,
    *,
    crs: str | None = None,
    longitude: Iterable[float] | np.ndarray | None = None,
    latitude: Iterable[float] | np.ndarray | None = None,
    altitude_m: Iterable[float] | np.ndarray | None = None,
    allow_lonlat_inference: bool = True,
) -> GeographicCoordinates:
    """Return WGS84 coordinates without silently applying an unknown transform.

    Priority is explicit latitude/longitude, then EPSG:4326 X/Y, then WGS84 UTM
    EPSG:326xx/327xx.  As a final safe convenience, numeric X/Y confined to
    geographic ranges can be inferred as longitude/latitude.
    """

    if longitude is not None and latitude is not None:
        lon = _as_float(longitude)
        lat = _as_float(latitude, lon.size)
        alt = _as_float(altitude_m, lon.size) if altitude_m is not None else np.zeros(lon.size, dtype=float)
        return GeographicCoordinates(lon, lat, np.nan_to_num(alt, nan=0.0), "EPSG:4326")

    xx = _as_float(x)
    yy = _as_float(y, xx.size)
    alt = _as_float(altitude_m, xx.size) if altitude_m is not None else np.zeros(xx.size, dtype=float)
    normalized = normalize_crs(crs)

    if normalized == "EPSG:4326":
        return GeographicCoordinates(xx, yy, np.nan_to_num(alt, nan=0.0), normalized)

    match = re.fullmatch(r"EPSG:(326|327)(\d{2})", normalized)
    if match:
        zone = int(match.group(2))
        if not 1 <= zone <= 60:
            raise CoordinateTransformError(f"Invalid WGS84 UTM zone in {normalized!r}.")
        northern = match.group(1) == "326"
        lon, lat = utm_wgs84_to_lonlat(xx, yy, zone=zone, northern=northern)
        return GeographicCoordinates(lon, lat, np.nan_to_num(alt, nan=0.0), normalized)

    valid = np.isfinite(xx) & np.isfinite(yy)
    if allow_lonlat_inference and np.any(valid):
        if np.all((xx[valid] >= -180.0) & (xx[valid] <= 180.0)) and np.all(
            (yy[valid] >= -90.0) & (yy[valid] <= 90.0)
        ):
            return GeographicCoordinates(xx, yy, np.nan_to_num(alt, nan=0.0), "EPSG:4326 (inferred)")

    raise CoordinateTransformError(
        "Satellite/3D basemaps require WGS84 longitude/latitude or a WGS84 UTM CRS "
        "(EPSG:326xx/327xx). Define the dataset CRS before enabling the basemap."
    )


def utm_wgs84_to_lonlat(
    easting: Iterable[float] | np.ndarray,
    northing: Iterable[float] | np.ndarray,
    *,
    zone: int,
    northern: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized inverse WGS84 / UTM conversion.

    Formula follows the standard Transverse Mercator inverse series using the
    WGS84 ellipsoid (a=6378137 m, 1/f=298.257223563) and UTM scale 0.9996.
    """

    e = _as_float(easting)
    n = _as_float(northing, e.size)
    if not 1 <= int(zone) <= 60:
        raise CoordinateTransformError("UTM zone must be in the range 1..60.")

    a = 6378137.0
    f = 1.0 / 298.257223563
    ecc_sq = f * (2.0 - f)
    ecc_prime_sq = ecc_sq / (1.0 - ecc_sq)
    k0 = 0.9996

    x = e - 500000.0
    y = n.copy()
    if not northern:
        y = y - 10000000.0

    m = y / k0
    mu = m / (a * (1.0 - ecc_sq / 4.0 - 3.0 * ecc_sq**2 / 64.0 - 5.0 * ecc_sq**3 / 256.0))

    e1 = (1.0 - np.sqrt(1.0 - ecc_sq)) / (1.0 + np.sqrt(1.0 - ecc_sq))
    j1 = 3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0
    j2 = 21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0
    j3 = 151.0 * e1**3 / 96.0
    j4 = 1097.0 * e1**4 / 512.0
    fp = mu + j1 * np.sin(2.0 * mu) + j2 * np.sin(4.0 * mu) + j3 * np.sin(6.0 * mu) + j4 * np.sin(8.0 * mu)

    sin_fp = np.sin(fp)
    cos_fp = np.cos(fp)
    tan_fp = np.tan(fp)
    c1 = ecc_prime_sq * cos_fp**2
    t1 = tan_fp**2
    n1 = a / np.sqrt(1.0 - ecc_sq * sin_fp**2)
    r1 = a * (1.0 - ecc_sq) / np.power(1.0 - ecc_sq * sin_fp**2, 1.5)
    d = x / (n1 * k0)

    q1 = n1 * tan_fp / r1
    q2 = d**2 / 2.0
    q3 = (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1**2 - 9.0 * ecc_prime_sq) * d**4 / 24.0
    q4 = (
        61.0
        + 90.0 * t1
        + 298.0 * c1
        + 45.0 * t1**2
        - 252.0 * ecc_prime_sq
        - 3.0 * c1**2
    ) * d**6 / 720.0
    lat = fp - q1 * (q2 - q3 + q4)

    q5 = d
    q6 = (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
    q7 = (
        5.0
        - 2.0 * c1
        + 28.0 * t1
        - 3.0 * c1**2
        + 8.0 * ecc_prime_sq
        + 24.0 * t1**2
    ) * d**5 / 120.0
    lon_origin = np.deg2rad((int(zone) - 1) * 6 - 180 + 3)
    lon = lon_origin + (q5 - q6 + q7) / cos_fp

    return np.rad2deg(lon), np.rad2deg(lat)


def decimate_indices(count: int, maximum_points: int = 5000) -> np.ndarray:
    count = max(0, int(count))
    maximum_points = max(2, int(maximum_points))
    if count <= maximum_points:
        return np.arange(count, dtype=int)
    return np.unique(np.linspace(0, count - 1, maximum_points).round().astype(int))
