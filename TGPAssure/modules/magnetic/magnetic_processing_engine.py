from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from modules.magnetic.constants import (
    BASE_TOTAL_FIELD,
    DESPIKED_TOTAL_FIELD,
    DIURNAL_CORRECTED_FIELD,
    DIURNAL_CORRECTION,
    IGRF_TOTAL_FIELD,
    LEVELED_FIELD,
    MICROLEVELED_FIELD,
    RAW_TOTAL_FIELD,
    RESIDUAL_FIELD,
)
from modules.magnetic.exceptions import MagneticProcessingError
from modules.magnetic.models import MagneticDataset
from modules.magnetic.utils import local_metric_xy, median_mad


class MagneticProcessingEngine:
    """Traceable processing operations for magnetic datasets.

    Every operation creates a derived channel and appends provenance. The raw
    total-field channel is never overwritten.
    """

    @staticmethod
    def _rolling_median(values: np.ndarray, window: int) -> np.ndarray:
        window = max(3, int(window) | 1)
        half = window // 2
        finite = np.isfinite(values)
        fill = float(np.nanmedian(values[finite])) if np.any(finite) else 0.0
        working = np.where(finite, values, fill)
        padded = np.pad(working, (half, half), mode="edge")
        return np.asarray([np.median(padded[index:index + window]) for index in range(values.size)], dtype=float)

    def despike(
        self,
        dataset: MagneticDataset,
        *,
        source_channel: str = RAW_TOTAL_FIELD,
        output_channel: str = DESPIKED_TOTAL_FIELD,
        window: int = 7,
        outlier_factor: float = 6.0,
        absolute_limit_nt: float = 20.0,
    ) -> np.ndarray:
        values = dataset.channel(source_channel)
        local = self._rolling_median(values, window)
        residual = values - local
        median, mad = median_mad(residual)
        robust_limit = outlier_factor * 1.4826 * mad if np.isfinite(mad) and mad > 0 else absolute_limit_nt
        limit = max(float(absolute_limit_nt), float(robust_limit))
        mask = np.isfinite(values) & (np.abs(residual - median) > limit)
        result = values.copy()
        result[mask] = local[mask]
        dataset.add_derived_channel(
            output_channel,
            result,
            parent_channel=source_channel,
            operation="hampel_despike",
            parameters={"window": window, "outlier_factor": outlier_factor, "absolute_limit_nt": absolute_limit_nt, "replaced_count": int(np.count_nonzero(mask))},
            overwrite=output_channel in dataset.channels,
        )
        dataset.set_quality_flag("despike_replaced", mask)
        return mask

    def interpolate_base(
        self,
        rover: MagneticDataset,
        base: MagneticDataset,
        *,
        maximum_gap_s: float = 30.0,
        allow_extrapolation: bool = False,
    ) -> np.ndarray:
        base_values = base.channel(BASE_TOTAL_FIELD)
        base_valid = np.isfinite(base_values) & ~np.isnat(base.timestamps)
        rover_valid = ~np.isnat(rover.timestamps)
        if np.count_nonzero(base_valid) < 2:
            raise MagneticProcessingError("At least two valid base-station records are required")
        base_time = base.timestamps[base_valid].astype("datetime64[ms]").astype(np.int64).astype(float) / 1000.0
        field = base_values[base_valid]
        order = np.argsort(base_time)
        base_time, field = base_time[order], field[order]
        unique_time, unique_index = np.unique(base_time, return_index=True)
        base_time, field = unique_time, field[unique_index]
        rover_time = rover.timestamps.astype("datetime64[ms]").astype(np.int64).astype(float) / 1000.0
        interpolated = np.full(rover.record_count, np.nan, dtype=float)
        interpolated[rover_valid] = np.interp(rover_time[rover_valid], base_time, field)
        if not allow_extrapolation:
            outside = rover_valid & ((rover_time < base_time[0]) | (rover_time > base_time[-1]))
            interpolated[outside] = np.nan
        insertion = np.searchsorted(base_time, rover_time, side="left")
        left = np.clip(insertion - 1, 0, base_time.size - 1)
        right = np.clip(insertion, 0, base_time.size - 1)
        bracketing_gap = base_time[right] - base_time[left]
        unsupported = rover_valid & (bracketing_gap > maximum_gap_s)
        interpolated[unsupported] = np.nan
        return interpolated

    def apply_diurnal_correction(
        self,
        rover: MagneticDataset,
        base: MagneticDataset,
        *,
        source_channel: str | None = None,
        reference: str = "median",
        maximum_gap_s: float = 30.0,
        allow_extrapolation: bool = False,
    ) -> np.ndarray:
        source_channel = source_channel or (DESPIKED_TOTAL_FIELD if DESPIKED_TOTAL_FIELD in rover.channels else RAW_TOTAL_FIELD)
        source = rover.channel(source_channel)
        interpolated = self.interpolate_base(rover, base, maximum_gap_s=maximum_gap_s, allow_extrapolation=allow_extrapolation)
        valid_base = np.isfinite(interpolated)
        if not np.any(valid_base):
            raise MagneticProcessingError("Base interpolation produced no supported rover records")
        if reference == "first":
            reference_value = float(interpolated[np.flatnonzero(valid_base)[0]])
        elif reference == "mean":
            reference_value = float(np.nanmean(interpolated))
        else:
            reference_value = float(np.nanmedian(interpolated))
        correction = interpolated - reference_value
        corrected = source - correction
        rover.add_derived_channel(
            DIURNAL_CORRECTION,
            correction,
            parent_channel=BASE_TOTAL_FIELD,
            operation="base_interpolation",
            parameters={"reference": reference, "reference_value_nt": reference_value, "maximum_gap_s": maximum_gap_s, "allow_extrapolation": allow_extrapolation},
            overwrite=DIURNAL_CORRECTION in rover.channels,
        )
        rover.add_derived_channel(
            DIURNAL_CORRECTED_FIELD,
            corrected,
            parent_channel=source_channel,
            operation="diurnal_correction",
            parameters={"base_source": str(base.source_path), "reference_value_nt": reference_value},
            overwrite=DIURNAL_CORRECTED_FIELD in rover.channels,
        )
        rover.set_quality_flag("base_interpolation_unsupported", ~valid_base)
        return corrected

    def remove_igrf(
        self,
        dataset: MagneticDataset,
        igrf_total: float | Iterable[float] | np.ndarray,
        *,
        source_channel: str | None = None,
    ) -> np.ndarray:
        source_channel = source_channel or (DIURNAL_CORRECTED_FIELD if DIURNAL_CORRECTED_FIELD in dataset.channels else RAW_TOTAL_FIELD)
        source = dataset.channel(source_channel)
        igrf = np.asarray(igrf_total, dtype=float)
        if igrf.ndim == 0:
            igrf = np.full(dataset.record_count, float(igrf), dtype=float)
        if igrf.ndim != 1 or igrf.size != dataset.record_count:
            raise MagneticProcessingError("IGRF values must be a scalar or one value per rover record")
        residual = source - igrf
        dataset.add_derived_channel(IGRF_TOTAL_FIELD, igrf, parent_channel=None, operation="external_igrf_model", parameters={}, overwrite=IGRF_TOTAL_FIELD in dataset.channels)
        dataset.add_derived_channel(RESIDUAL_FIELD, residual, parent_channel=source_channel, operation="igrf_removal", parameters={}, overwrite=RESIDUAL_FIELD in dataset.channels)
        return residual

    def level_lines(
        self,
        dataset: MagneticDataset,
        *,
        source_channel: str | None = None,
        output_channel: str = LEVELED_FIELD,
        reference: str = "crossover_network",
    ) -> dict[str, float]:
        """Level survey lines using crossover differences when geometry is available.

        Constant per-line corrections are solved as a least-squares network from
        line/tie-line crossover mismatches.  This is substantially safer than
        forcing every line to the same median, which can remove genuine regional
        magnetic gradients.  A robust median fallback is used only when no usable
        crossover network can be built.
        """
        source_channel = source_channel or (
            RESIDUAL_FIELD if RESIDUAL_FIELD in dataset.channels else
            DIURNAL_CORRECTED_FIELD if DIURNAL_CORRECTED_FIELD in dataset.channels else
            RAW_TOTAL_FIELD
        )
        values = dataset.channel(source_channel)
        groups = dataset.line_groups()
        if not groups:
            raise MagneticProcessingError("Line identifiers are required for leveling")

        valid_groups = {line: idx for line, idx in groups.items() if np.any(np.isfinite(values[idx]))}
        if not valid_groups:
            raise MagneticProcessingError("No valid line data are available for leveling")

        corrections: dict[str, float] = {}
        crossover_count = 0
        residual_rms = None

        coord_mask = dataset.valid_coordinate_mask()
        if np.count_nonzero(coord_mask) >= 4 and len(valid_groups) >= 2:
            try:
                from scipy.spatial import cKDTree

                # Estimate a realistic crossover search radius from within-line spacing.
                spacings = []
                for idx in valid_groups.values():
                    good = idx[np.isfinite(dataset.x[idx]) & np.isfinite(dataset.y[idx])]
                    if good.size > 1:
                        dx = np.diff(dataset.x[good]); dy = np.diff(dataset.y[good])
                        d = np.hypot(dx, dy); d = d[np.isfinite(d) & (d > 0)]
                        if d.size:
                            spacings.append(float(np.nanmedian(d)))
                median_spacing = float(np.nanmedian(spacings)) if spacings else 1.0
                search_radius = max(1e-6, median_spacing * 1.75)

                lines = list(valid_groups)
                equations = []
                rhs = []
                weights = []
                crossover_meta = []
                line_types = dataset.line_type.astype(str) if dataset.line_type is not None else None

                for ia, line_a in enumerate(lines):
                    idx_a = valid_groups[line_a]
                    good_a = idx_a[np.isfinite(dataset.x[idx_a]) & np.isfinite(dataset.y[idx_a]) & np.isfinite(values[idx_a])]
                    if good_a.size == 0:
                        continue
                    pts_a = np.column_stack([dataset.x[good_a], dataset.y[good_a]])
                    for ib in range(ia + 1, len(lines)):
                        line_b = lines[ib]
                        idx_b = valid_groups[line_b]
                        good_b = idx_b[np.isfinite(dataset.x[idx_b]) & np.isfinite(dataset.y[idx_b]) & np.isfinite(values[idx_b])]
                        if good_b.size == 0:
                            continue

                        # Prefer traverse-vs-tie/control relationships when line-type
                        # metadata exists, but still allow unknown legacy datasets.
                        if line_types is not None:
                            ta = {str(v).lower() for v in line_types[idx_a] if str(v)}
                            tb = {str(v).lower() for v in line_types[idx_b] if str(v)}
                            known_a = ta - {"unknown", ""}; known_b = tb - {"unknown", ""}
                            if known_a and known_b:
                                a_tie = bool(known_a & {"tie", "control"}); b_tie = bool(known_b & {"tie", "control"})
                                if a_tie == b_tie:
                                    continue

                        pts_b = np.column_stack([dataset.x[good_b], dataset.y[good_b]])
                        tree = cKDTree(pts_b)
                        dist, nearest = tree.query(pts_a, k=1)
                        if dist.size == 0:
                            continue
                        k = int(np.argmin(dist)); dmin = float(dist[k])
                        if not np.isfinite(dmin) or dmin > search_radius:
                            continue
                        pa = int(good_a[k]); pb = int(good_b[int(nearest[k])])
                        diff = float(values[pa] - values[pb])
                        if not np.isfinite(diff):
                            continue
                        row = np.zeros(len(lines), dtype=float)
                        # Va + ca = Vb + cb  -> ca - cb = Vb - Va = -diff
                        row[ia] = 1.0; row[ib] = -1.0
                        equations.append(row); rhs.append(-diff)
                        # closer crossovers receive slightly higher weight
                        weights.append(1.0 / max(1.0, dmin / max(median_spacing, 1e-9)))
                        crossover_meta.append((line_a, line_b, dmin, diff))

                if equations and len(equations) >= max(1, len(lines) - 1):
                    A = np.vstack(equations); b = np.asarray(rhs, dtype=float); w = np.sqrt(np.asarray(weights, dtype=float))
                    Aw = A * w[:, None]; bw = b * w
                    # Zero-mean correction constraint removes the arbitrary network datum.
                    constraint = np.ones((1, len(lines)), dtype=float) / max(1, len(lines))
                    Aw = np.vstack([Aw, constraint * max(1.0, np.sqrt(len(equations)))])
                    bw = np.concatenate([bw, [0.0]])
                    solution, *_ = np.linalg.lstsq(Aw, bw, rcond=None)
                    corrections = {line: float(solution[i]) for i, line in enumerate(lines)}
                    crossover_count = len(equations)
                    residuals = A @ solution - b
                    residual_rms = float(np.sqrt(np.mean(residuals ** 2))) if residuals.size else 0.0
            except Exception:
                corrections = {}

        if not corrections:
            # Fallback for datasets lacking valid XY/tie-line geometry. This is
            # intentionally marked as a fallback because median leveling can
            # suppress real long-wavelength geology.
            line_medians = {line: float(np.nanmedian(values[idx])) for line, idx in valid_groups.items()}
            target = float(np.nanmedian(list(line_medians.values())))
            corrections = {line: target - median for line, median in line_medians.items()}
            reference = "robust_line_median_fallback"

        result = values.copy()
        for line, indices in groups.items():
            if line in corrections:
                result[indices] = result[indices] + corrections[line]

        dataset.add_derived_channel(
            output_channel,
            result,
            parent_channel=source_channel,
            operation="crossover_line_leveling" if crossover_count else "constant_line_leveling_fallback",
            parameters={
                "reference": reference,
                "line_corrections_nt": corrections,
                "crossover_count": crossover_count,
                "crossover_residual_rms_nt": residual_rms,
            },
            overwrite=output_channel in dataset.channels,
        )
        return corrections

    def microlevel(
        self,
        dataset: MagneticDataset,
        *,
        source_channel: str = LEVELED_FIELD,
        output_channel: str = MICROLEVELED_FIELD,
        polynomial_order: int = 1,
        maximum_correction_nt: float = 10.0,
    ) -> dict[str, float]:
        values = dataset.channel(source_channel)
        groups = dataset.line_groups()
        if not groups:
            raise MagneticProcessingError("Line identifiers are required for microleveling")
        result = values.copy()
        correction_summary: dict[str, float] = {}
        for line, indices in groups.items():
            line_values = values[indices]
            valid = np.isfinite(line_values)
            if np.count_nonzero(valid) <= polynomial_order + 2:
                continue
            x = np.linspace(-1.0, 1.0, line_values.size)
            coefficients = np.polyfit(x[valid], line_values[valid], polynomial_order)
            trend = np.polyval(coefficients, x)
            trend -= float(np.nanmedian(trend[valid]))
            trend = np.clip(trend, -maximum_correction_nt, maximum_correction_nt)
            result[indices] = line_values - trend
            correction_summary[line] = float(np.nanmax(np.abs(trend)))
        dataset.add_derived_channel(
            output_channel,
            result,
            parent_channel=source_channel,
            operation="bounded_line_microlevel",
            parameters={"polynomial_order": polynomial_order, "maximum_correction_nt": maximum_correction_nt, "line_max_corrections_nt": correction_summary},
            overwrite=output_channel in dataset.channels,
        )
        return correction_summary

    def grid(
        self,
        dataset: MagneticDataset,
        *,
        source_channel: str | None = None,
        cell_size: float | None = None,
        method: str = "linear",
        padding_cells: int = 1,
    ) -> dict[str, Any]:
        if str(dataset.metadata.get("acquisition_classification", "moving")).lower() == "stationary":
            raise MagneticProcessingError(
                "This dataset is classified as stationary/static. Magnetic gridding requires a spatial rover survey with meaningful station coverage."
            )
        source_channel = source_channel or (MICROLEVELED_FIELD if MICROLEVELED_FIELD in dataset.channels else LEVELED_FIELD if LEVELED_FIELD in dataset.channels else RESIDUAL_FIELD if RESIDUAL_FIELD in dataset.channels else DIURNAL_CORRECTED_FIELD if DIURNAL_CORRECTED_FIELD in dataset.channels else RAW_TOTAL_FIELD)
        values = dataset.channel(source_channel)
        valid = dataset.valid_coordinate_mask() & np.isfinite(values)
        if np.count_nonzero(valid) < 3:
            raise MagneticProcessingError("At least three coordinate-field records are required for gridding")
        source_x, source_y, z = dataset.x[valid], dataset.y[valid], values[valid]
        geographic = bool(dataset.crs and ("4326" in dataset.crs or "wgs84" in dataset.crs.lower()))
        x, y = local_metric_xy(source_x, source_y, geographic=geographic)
        if cell_size is None:
            coordinate_steps = np.hypot(np.diff(x), np.diff(y))
            positive = coordinate_steps[coordinate_steps > 0]
            cell_size = float(np.median(positive)) if positive.size else 25.0
        if cell_size <= 0:
            raise MagneticProcessingError("Grid cell size must be positive")
        min_x, max_x = float(np.min(x)), float(np.max(x))
        min_y, max_y = float(np.min(y)), float(np.max(y))
        grid_x = np.arange(min_x - padding_cells * cell_size, max_x + (padding_cells + 1) * cell_size, cell_size)
        grid_y = np.arange(min_y - padding_cells * cell_size, max_y + (padding_cells + 1) * cell_size, cell_size)
        xx, yy = np.meshgrid(grid_x, grid_y)
        try:
            from scipy.interpolate import griddata
            selected_method = method if method in {"linear", "nearest", "cubic"} else "linear"
            grid_values = griddata(np.column_stack((x, y)), z, (xx, yy), method=selected_method)
            if selected_method != "nearest" and np.any(~np.isfinite(grid_values)):
                nearest = griddata(np.column_stack((x, y)), z, (xx, yy), method="nearest")
                outside_linear = ~np.isfinite(grid_values)
                extrapolated_pct = 100.0 * np.count_nonzero(outside_linear) / grid_values.size
                grid_values[outside_linear] = nearest[outside_linear]
            else:
                extrapolated_pct = 0.0
        except ImportError:
            grid_values = self._idw_grid(x, y, z, xx, yy)
            extrapolated_pct = 0.0
        return {
            "values": grid_values,
            "x": grid_x,
            "y": grid_y,
            "cell_size": float(cell_size),
            "source_channel": source_channel,
            "method": method,
            "crs": dataset.crs if not geographic else "LOCAL_METRIC_FROM_EPSG:4326",
            "source_crs": dataset.crs,
            "coordinate_units": "m",
            "local_metric_origin": {
                "longitude_deg": float(np.nanmedian(source_x)) if geographic else None,
                "latitude_deg": float(np.nanmedian(source_y)) if geographic else None,
            },
            "extrapolated_pct": extrapolated_pct,
        }

    @staticmethod
    def _idw_grid(x: np.ndarray, y: np.ndarray, z: np.ndarray, xx: np.ndarray, yy: np.ndarray, power: float = 2.0) -> np.ndarray:
        output = np.empty_like(xx, dtype=float)
        for row in range(xx.shape[0]):
            dx = xx[row, :, None] - x[None, :]
            dy = yy[row, :, None] - y[None, :]
            distance_sq = dx * dx + dy * dy
            exact = distance_sq == 0
            weights = 1.0 / np.maximum(distance_sq, 1e-12) ** (power / 2.0)
            values = np.sum(weights * z[None, :], axis=1) / np.sum(weights, axis=1)
            for column in np.flatnonzero(np.any(exact, axis=1)):
                values[column] = z[np.flatnonzero(exact[column])[0]]
            output[row] = values
        return output

    def export_csv(self, dataset: MagneticDataset, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        channel_names = list(dataset.channel_names)
        headers = ["timestamp", "x", "y", "elevation", "line_id", "station_id", "line_type", *channel_names]
        with output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            for index in range(dataset.record_count):
                writer.writerow([
                    str(dataset.timestamps[index]), dataset.x[index], dataset.y[index], dataset.elevation[index],
                    dataset.line_id[index], dataset.station_id[index], dataset.line_type[index],
                    *[dataset.channels[name][index] for name in channel_names],
                ])
        return output
