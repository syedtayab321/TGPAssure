from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import griddata


@dataclass(frozen=True)
class GriddedSurface:
    """Regular display grid derived from scattered observations.

    The grid is intended for visualization only. ``inside_hull`` identifies cells
    supported by linear interpolation; nearest-neighbour values are used only to
    keep the OpenGL mesh numerically well-formed and must remain transparent
    outside that mask.
    """

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    values: np.ndarray
    inside_hull: np.ndarray


def finite_xyzv(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    z: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x_arr = np.asarray(x, dtype=float).ravel()
    y_arr = np.asarray(y, dtype=float).ravel()
    v_arr = np.asarray(values, dtype=float).ravel()
    if z is None:
        z_arr = np.zeros_like(v_arr, dtype=float)
    else:
        z_arr = np.asarray(z, dtype=float).ravel()
    n = min(x_arr.size, y_arr.size, z_arr.size, v_arr.size)
    x_arr, y_arr, z_arr, v_arr = x_arr[:n], y_arr[:n], z_arr[:n], v_arr[:n]
    valid = np.isfinite(x_arr) & np.isfinite(y_arr) & np.isfinite(v_arr)
    # Missing elevation is not a reason to discard a valid XY/value observation.
    z_arr = np.where(np.isfinite(z_arr), z_arr, 0.0)
    return x_arr[valid], y_arr[valid], z_arr[valid], v_arr[valid]


def robust_limits(values: np.ndarray, lower: float = 2.0, upper: float = 98.0) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return 0.0, 1.0
    if finite.size < 5:
        low, high = float(np.min(finite)), float(np.max(finite))
    else:
        low, high = (float(v) for v in np.percentile(finite, [lower, upper]))
    if not np.isfinite(low) or not np.isfinite(high):
        return 0.0, 1.0
    if high <= low:
        pad = max(abs(low) * 0.01, 1.0)
        return low - pad, high + pad
    return low, high


def normalize_robust(values: np.ndarray, lower: float = 2.0, upper: float = 98.0) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    low, high = robust_limits(arr, lower, upper)
    with np.errstate(invalid="ignore"):
        result = (arr - low) / (high - low)
    return np.clip(result, 0.0, 1.0)


def deterministic_decimation_indices(count: int, maximum: int) -> np.ndarray:
    count = int(max(0, count))
    maximum = int(max(1, maximum))
    if count <= maximum:
        return np.arange(count, dtype=int)
    return np.unique(np.linspace(0, count - 1, maximum).astype(int))


def value_relief(
    values: np.ndarray,
    horizontal_span: float,
    scale_fraction: float = 0.12,
) -> np.ndarray:
    """Return a centered, unit-safe display relief derived from values.

    This deliberately does not mix physical value units (for example nT) with
    metres. Values are robustly normalized to [-1, 1] and then scaled to a
    documented fraction of the XY footprint solely for 3D visual emphasis.
    """

    normalized = normalize_robust(values) * 2.0 - 1.0
    span = float(horizontal_span) if np.isfinite(horizontal_span) and horizontal_span > 0 else 1.0
    return normalized * span * float(max(0.0, scale_fraction))



def geographic_to_local_xy(longitude: np.ndarray, latitude: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Convert lon/lat degrees to a local metric tangent-plane approximation.

    This equirectangular projection is used only for interactive local display, not
    for survey computation or coordinate transformation deliverables. It is stable
    for normal project-scale extents and preserves metre-like OpenGL aspect ratios.
    """
    lon = np.asarray(longitude, dtype=float)
    lat = np.asarray(latitude, dtype=float)
    valid = np.isfinite(lon) & np.isfinite(lat)
    if not np.any(valid):
        return np.full_like(lon, np.nan), np.full_like(lat, np.nan), float("nan"), float("nan")
    lon0 = float(np.nanmedian(lon[valid]))
    lat0 = float(np.nanmedian(lat[valid]))
    radius = 6378137.0
    x = np.deg2rad(lon - lon0) * radius * np.cos(np.deg2rad(lat0))
    y = np.deg2rad(lat - lat0) * radius
    return x, y, lon0, lat0


def grid_scattered_surface(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    values: np.ndarray,
    *,
    max_cells: int = 90,
) -> GriddedSurface | None:
    """Interpolate scattered XYZ/value observations onto a regular display grid.

    Linear interpolation is used inside the convex hull. Nearest-neighbour values
    only fill numerical holes for OpenGL; ``inside_hull`` must be used as alpha so
    unsupported extrapolated cells are not presented as measured/interpolated data.
    """

    x_arr, y_arr, z_arr, v_arr = finite_xyzv(x, y, values, z)
    if x_arr.size < 4:
        return None
    points = np.column_stack((x_arr, y_arr))
    # A surface needs two-dimensional spatial support, not a single collinear line.
    centered = points - np.mean(points, axis=0)
    if np.linalg.matrix_rank(centered) < 2:
        return None
    unique_points, unique_idx = np.unique(np.round(points, decimals=9), axis=0, return_index=True)
    if unique_points.shape[0] < 4:
        return None
    x_arr = x_arr[unique_idx]
    y_arr = y_arr[unique_idx]
    z_arr = z_arr[unique_idx]
    v_arr = v_arr[unique_idx]
    points = np.column_stack((x_arr, y_arr))

    grid_n = int(np.clip(np.sqrt(points.shape[0]) * 2.0, 20, max_cells))
    gx = np.linspace(float(np.min(x_arr)), float(np.max(x_arr)), grid_n)
    gy = np.linspace(float(np.min(y_arr)), float(np.max(y_arr)), grid_n)
    xx, yy = np.meshgrid(gx, gy, indexing="ij")

    try:
        z_linear = griddata(points, z_arr, (xx, yy), method="linear")
        v_linear = griddata(points, v_arr, (xx, yy), method="linear")
        inside = np.isfinite(v_linear)
        if not np.any(inside):
            return None
        z_nearest = griddata(points, z_arr, (xx, yy), method="nearest")
        v_nearest = griddata(points, v_arr, (xx, yy), method="nearest")
    except Exception:
        return None

    z_grid = np.where(np.isfinite(z_linear), z_linear, z_nearest)
    v_grid = np.where(np.isfinite(v_linear), v_linear, v_nearest)
    return GriddedSurface(gx, gy, z_grid, v_grid, inside)
