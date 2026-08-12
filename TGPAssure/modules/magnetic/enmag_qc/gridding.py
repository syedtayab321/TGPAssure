from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from modules.magnetic.enmag_qc.models import ColorRange, GridResult


def finite_range(values: np.ndarray) -> tuple[float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("No finite values are available")
    lo = float(np.nanmin(finite))
    hi = float(np.nanmax(finite))
    if hi <= lo:
        hi = lo + max(abs(lo) * 1e-9, 1e-9)
    return lo, hi


def robust_range(values: np.ndarray, *, low_percentile: float = 2.0, high_percentile: float = 98.0) -> tuple[float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("No finite values are available")
    lo, hi = np.nanpercentile(finite, [low_percentile, high_percentile])
    lo = float(lo)
    hi = float(hi)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return finite_range(finite)
    return lo, hi


def make_color_range(values: np.ndarray, mode: str, manual_min: float | None, manual_max: float | None, *, unit: str) -> ColorRange:
    data_min, data_max = finite_range(values)
    normalised = (mode or "Robust Auto").strip().lower()
    if normalised == "manual":
        if manual_min is None or manual_max is None:
            raise ValueError("Manual Color Min and Color Max are required")
        if not np.isfinite(manual_min) or not np.isfinite(manual_max) or manual_max <= manual_min:
            raise ValueError("Manual Color Max must be greater than Color Min")
        scale_min, scale_max = float(manual_min), float(manual_max)
    elif normalised in {"auto", "full range", "full auto"}:
        scale_min, scale_max = data_min, data_max
    else:
        scale_min, scale_max = robust_range(values)
    return ColorRange(data_min, data_max, scale_min, scale_max, mode, unit)


def _normalised_cell_coordinates(
    x: np.ndarray,
    y: np.ndarray,
    *,
    cols: int,
    rows: int,
    bounds: tuple[float, float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    xmin, xmax, ymin, ymax = bounds
    cx = (np.asarray(x, dtype=float) - xmin) / max(xmax - xmin, 1e-15) * max(cols - 1, 1)
    # Row zero is north/top.
    cy = (ymax - np.asarray(y, dtype=float)) / max(ymax - ymin, 1e-15) * max(rows - 1, 1)
    return cx, cy


def _grid_definition(x: np.ndarray, y: np.ndarray, cols: int, rows: int) -> tuple[tuple[float, float, float, float], np.ndarray, np.ndarray]:
    xmin = float(np.nanmin(x))
    xmax = float(np.nanmax(x))
    ymin = float(np.nanmin(y))
    ymax = float(np.nanmax(y))
    if xmax <= xmin:
        xmax = xmin + 1.0
    if ymax <= ymin:
        ymax = ymin + 1.0
    gx = np.linspace(xmin, xmax, cols, dtype=float)
    gy = np.linspace(ymax, ymin, rows, dtype=float)
    return (xmin, xmax, ymin, ymax), gx, gy


def _representative_index_per_cell(flat_cell: np.ndarray, source_indices: np.ndarray, cell_count: int) -> np.ndarray:
    rep = np.full(cell_count, -1, dtype=np.int64)
    if flat_cell.size == 0:
        return rep
    order = np.argsort(flat_cell, kind="stable")
    sorted_cells = flat_cell[order]
    first = np.r_[True, sorted_cells[1:] != sorted_cells[:-1]]
    rep[sorted_cells[first]] = source_indices[order[first]]
    return rep


def _circular_mean_bincount(flat: np.ndarray, values_deg: np.ndarray, cell_count: int) -> tuple[np.ndarray, np.ndarray]:
    radians = np.deg2rad(np.mod(values_deg, 360.0))
    sin_sum = np.bincount(flat, weights=np.sin(radians), minlength=cell_count)
    cos_sum = np.bincount(flat, weights=np.cos(radians), minlength=cell_count)
    count = np.bincount(flat, minlength=cell_count)
    angle = np.mod(np.rad2deg(np.arctan2(sin_sum, cos_sum)), 360.0)
    angle[count == 0] = np.nan
    return angle, count


def fast_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    source_indices: np.ndarray,
    *,
    cols: int,
    rows: int,
    point_radius: float,
    circular: bool = False,
) -> GridResult:
    bounds, gx, gy = _grid_definition(x, y, cols, rows)
    cx, cy = _normalised_cell_coordinates(x, y, cols=cols, rows=rows, bounds=bounds)
    ci = np.clip(np.rint(cx).astype(np.int64), 0, cols - 1)
    ri = np.clip(np.rint(cy).astype(np.int64), 0, rows - 1)
    flat = ri * cols + ci
    cell_count = rows * cols

    if circular:
        flat_values, counts = _circular_mean_bincount(flat, values, cell_count)
    else:
        sums = np.bincount(flat, weights=values, minlength=cell_count)
        counts = np.bincount(flat, minlength=cell_count)
        flat_values = np.full(cell_count, np.nan, dtype=float)
        occupied_1d = counts > 0
        flat_values[occupied_1d] = sums[occupied_1d] / counts[occupied_1d]

    grid = flat_values.reshape(rows, cols)
    occupied = counts.reshape(rows, cols) > 0
    reps = _representative_index_per_cell(flat, source_indices, cell_count).reshape(rows, cols)
    if not np.any(occupied):
        raise ValueError("No samples reached the output grid")

    distance, nearest_cells = ndimage.distance_transform_edt(~occupied, return_distances=True, return_indices=True)
    support = distance <= max(float(point_radius), 0.0)
    nearest_values = grid[nearest_cells[0], nearest_cells[1]]
    nearest_reps = reps[nearest_cells[0], nearest_cells[1]]
    out = np.full_like(grid, np.nan, dtype=float)
    nearest_source = np.full(grid.shape, -1, dtype=np.int64)
    out[support] = nearest_values[support]
    nearest_source[support] = nearest_reps[support]
    return GridResult(out, bounds, gx, gy, nearest_source, "Fast Grid")


def nearest_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    source_indices: np.ndarray,
    *,
    cols: int,
    rows: int,
    point_radius: float,
) -> GridResult:
    bounds, gx, gy = _grid_definition(x, y, cols, rows)
    px, py = _normalised_cell_coordinates(x, y, cols=cols, rows=rows, bounds=bounds)
    tree = cKDTree(np.column_stack((px, py)))
    cc, rr = np.meshgrid(np.arange(cols, dtype=float), np.arange(rows, dtype=float))
    query = np.column_stack((cc.ravel(), rr.ravel()))
    distance, index = tree.query(query, k=1, workers=-1)
    support = distance <= max(float(point_radius), 0.0)
    grid = np.full(query.shape[0], np.nan, dtype=float)
    nearest_source = np.full(query.shape[0], -1, dtype=np.int64)
    grid[support] = values[index[support]]
    nearest_source[support] = source_indices[index[support]]
    return GridResult(grid.reshape(rows, cols), bounds, gx, gy, nearest_source.reshape(rows, cols), "Nearest")


def idw_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    source_indices: np.ndarray,
    *,
    cols: int,
    rows: int,
    point_radius: float,
    power: float,
    circular: bool = False,
    neighbours: int = 16,
) -> GridResult:
    bounds, gx, gy = _grid_definition(x, y, cols, rows)
    px, py = _normalised_cell_coordinates(x, y, cols=cols, rows=rows, bounds=bounds)
    tree = cKDTree(np.column_stack((px, py)))
    cc, rr = np.meshgrid(np.arange(cols, dtype=float), np.arange(rows, dtype=float))
    query = np.column_stack((cc.ravel(), rr.ravel()))
    k = max(1, min(int(neighbours), values.size))
    distance, index = tree.query(query, k=k, workers=-1)
    if k == 1:
        distance = distance[:, None]
        index = index[:, None]
    nearest_distance = distance[:, 0]
    support = nearest_distance <= max(float(point_radius), 0.0)
    safe_distance = np.maximum(distance, 1e-12)
    weights = 1.0 / np.power(safe_distance, max(float(power), 0.05))
    # Exact sample/grid-node coincidences must not blend with neighbours.
    exact = distance <= 1e-12
    any_exact = np.any(exact, axis=1)
    if np.any(any_exact):
        weights[any_exact] = exact[any_exact].astype(float)
    denom = np.sum(weights, axis=1)
    if circular:
        radians = np.deg2rad(np.mod(values[index], 360.0))
        sin_mean = np.sum(weights * np.sin(radians), axis=1) / np.maximum(denom, 1e-15)
        cos_mean = np.sum(weights * np.cos(radians), axis=1) / np.maximum(denom, 1e-15)
        interpolated = np.mod(np.rad2deg(np.arctan2(sin_mean, cos_mean)), 360.0)
    else:
        interpolated = np.sum(weights * values[index], axis=1) / np.maximum(denom, 1e-15)
    out = np.full(query.shape[0], np.nan, dtype=float)
    nearest_source = np.full(query.shape[0], -1, dtype=np.int64)
    out[support] = interpolated[support]
    nearest_source[support] = source_indices[index[support, 0]]
    return GridResult(out.reshape(rows, cols), bounds, gx, gy, nearest_source.reshape(rows, cols), "IDW")


def grid_surface(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    source_indices: np.ndarray,
    *,
    cols: int,
    rows: int,
    point_radius: float,
    method: str,
    idw_power: float,
    circular: bool = False,
) -> GridResult:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    values = np.asarray(values, dtype=float)
    source_indices = np.asarray(source_indices, dtype=np.int64)
    if not (x.size == y.size == values.size == source_indices.size):
        raise ValueError("Gridding input arrays must have equal length")
    if values.size == 0:
        raise ValueError("No visible samples are available for interpolation")
    cols = max(2, int(cols))
    rows = max(2, int(rows))
    name = (method or "Fast Grid").strip().lower()
    if name == "idw":
        return idw_grid(x, y, values, source_indices, cols=cols, rows=rows, point_radius=point_radius, power=idw_power, circular=circular)
    if name == "nearest":
        return nearest_grid(x, y, values, source_indices, cols=cols, rows=rows, point_radius=point_radius)
    return fast_grid(x, y, values, source_indices, cols=cols, rows=rows, point_radius=point_radius, circular=circular)
