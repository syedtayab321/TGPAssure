from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from matplotlib.path import Path as MplPath
from scipy.spatial import cKDTree


FilterMode = Literal["ignore", "keep"]


def polygon_inside_mask(x: np.ndarray, y: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    vertices = np.asarray(vertices, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 2 or vertices.shape[0] < 3:
        return np.zeros(x.size, dtype=bool)
    finite = np.isfinite(x) & np.isfinite(y)
    result = np.zeros(x.size, dtype=bool)
    if np.any(finite):
        points = np.column_stack((x[finite], y[finite]))
        result[finite] = MplPath(vertices, closed=True).contains_points(points, radius=1e-12)
    return result


def apply_polygon_filter(base_mask: np.ndarray, inside_mask: np.ndarray, mode: FilterMode) -> np.ndarray:
    base = np.asarray(base_mask, dtype=bool)
    inside = np.asarray(inside_mask, dtype=bool)
    if base.size != inside.size:
        raise ValueError("Polygon selection mask length does not match the dataset")
    if mode == "keep":
        return base & inside
    return base & ~inside


@dataclass(slots=True)
class SpatialFilterDefinition:
    name: str
    vertices: np.ndarray
    mode: FilterMode

    def mask(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        inside = polygon_inside_mask(x, y, self.vertices)
        return inside if self.mode == "keep" else ~inside


class CoordinateIndex:
    """KD-tree for fluid hover queries with metric distance when possible."""

    def __init__(self, x: np.ndarray, y: np.ndarray, *, geographic: bool, coordinate_units: str = "") -> None:
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        finite = np.isfinite(self.x) & np.isfinite(self.y)
        self.source_indices = np.flatnonzero(finite)
        self.geographic = bool(geographic)
        self.coordinate_units = coordinate_units or "map units"
        if self.source_indices.size == 0:
            self.tree = None
            self._lon0 = self._lat0 = 0.0
            return
        if self.geographic:
            lon = self.x[self.source_indices]
            lat = self.y[self.source_indices]
            self._lon0 = float(np.nanmedian(lon))
            self._lat0 = float(np.nanmedian(lat))
            tx, ty = self._lonlat_to_local(lon, lat)
        else:
            self._lon0 = self._lat0 = 0.0
            tx = self.x[self.source_indices]
            ty = self.y[self.source_indices]
        self.tree = cKDTree(np.column_stack((tx, ty)))

    def _lonlat_to_local(self, lon: np.ndarray | float, lat: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
        radius = 6_371_008.8
        lon_arr = np.asarray(lon, dtype=float)
        lat_arr = np.asarray(lat, dtype=float)
        xx = radius * np.deg2rad(lon_arr - self._lon0) * np.cos(np.deg2rad(self._lat0))
        yy = radius * np.deg2rad(lat_arr - self._lat0)
        return xx, yy

    def query(self, x: float, y: float) -> tuple[int, float, str] | None:
        if self.tree is None:
            return None
        if self.geographic:
            qx, qy = self._lonlat_to_local(float(x), float(y))
            unit = "m"
        else:
            qx, qy = float(x), float(y)
            unit = "m" if (self.coordinate_units or "").lower() in {"m", "meter", "meters", "metre", "metres"} else self.coordinate_units
        distance, local_index = self.tree.query([float(qx), float(qy)], k=1)
        return int(self.source_indices[int(local_index)]), float(distance), unit or "map units"
