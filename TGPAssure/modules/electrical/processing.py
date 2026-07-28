from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from modules.electrical.models import ElectricalDataset


class ElectricalProcessingEngine:
    def derive_standard_fields(self, dataset: ElectricalDataset) -> ElectricalDataset:
        output = dataset.copy()
        n = output.record_count
        if n == 0:
            return output

        if not output.has("resistance_ohm") and output.has("voltage_mv") and output.has("current_ma"):
            current = output.numeric("current_ma")
            voltage = output.numeric("voltage_mv")
            resistance = np.full(n, np.nan)
            valid = np.isfinite(current) & np.isfinite(voltage) & (np.abs(current) > 1e-12)
            resistance[valid] = voltage[valid] / current[valid]  # mV / mA == ohm
            output.columns["resistance_ohm"] = resistance

        if {"a", "b", "m", "n"}.issubset(output.columns):
            factor = self.geometry_factor(output.numeric("a"), output.numeric("b"), output.numeric("m"), output.numeric("n"))
            output.columns["geometry_factor_m"] = factor
            if not output.has("apparent_resistivity_ohm_m") and output.has("resistance_ohm"):
                output.columns["apparent_resistivity_ohm_m"] = factor * output.numeric("resistance_ohm")
            positions = np.vstack([output.numeric(k) for k in ("a", "b", "m", "n")])
            output.columns["pseudo_x"] = np.nanmean(positions, axis=0)
            output.columns["pseudo_depth"] = 0.25 * (np.nanmax(positions, axis=0) - np.nanmin(positions, axis=0))
            array_types = self.classify_array_types(
                output.numeric("a"), output.numeric("b"), output.numeric("m"), output.numeric("n")
            )
            if output.has("array_type"):
                output.columns["array_type_inferred"] = array_types
                source_types = output.text("array_type")
            else:
                output.columns["array_type"] = array_types
                source_types = array_types
            labels, counts = np.unique(source_types[source_types != ""], return_counts=True)
            output.metadata["array_type_counts"] = {str(label): int(count) for label, count in zip(labels, counts)}
        elif output.has("ab2_m"):
            ab2 = output.numeric("ab2_m")
            output.columns["pseudo_x"] = output.numeric("station") if output.has("station") else np.arange(n, dtype=float)
            output.columns["pseudo_depth"] = 0.4 * ab2
        elif not output.has("pseudo_x"):
            if output.has("station"):
                output.columns["pseudo_x"] = output.numeric("station")
            elif output.has("easting"):
                output.columns["pseudo_x"] = output.numeric("easting")
            else:
                output.columns["pseudo_x"] = np.arange(n, dtype=float)

        reciprocal_error, reciprocal_count = self.reciprocal_errors(output)
        if reciprocal_count:
            output.columns["reciprocal_error_pct"] = reciprocal_error
            output.metadata["reciprocal_pair_count"] = reciprocal_count
        return output

    @staticmethod
    def geometry_factor(a: np.ndarray, b: np.ndarray, m: np.ndarray, n: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            am = np.abs(a - m)
            an = np.abs(a - n)
            bm = np.abs(b - m)
            bn = np.abs(b - n)
            denominator = (1.0 / am) - (1.0 / an) - (1.0 / bm) + (1.0 / bn)
            factor = (2.0 * np.pi) / denominator
        invalid = (~np.isfinite(factor)) | (am == 0) | (an == 0) | (bm == 0) | (bn == 0)
        factor[invalid] = np.nan
        return factor


    @staticmethod
    def classify_array_types(a: np.ndarray, b: np.ndarray, m: np.ndarray, n: np.ndarray) -> np.ndarray:
        """Classify common finite four-electrode geometries from electrode positions.

        The classifier is deliberately descriptive rather than authoritative. It
        recognizes common linear Wenner, Schlumberger-like and dipole-dipole
        layouts and labels everything else as General 4-electrode. Pole arrays
        require explicit remote/infinite-electrode metadata and are therefore not
        guessed from finite ABMN coordinates.
        """
        result = np.full(len(a), "", dtype=object)
        for i, values in enumerate(zip(a, b, m, n)):
            if not all(np.isfinite(values)):
                continue
            positions = {name: float(value) for name, value in zip(("A", "B", "M", "N"), values)}
            if len({round(value, 9) for value in positions.values()}) < 4:
                result[i] = "Invalid/coincident"
                continue
            ordered = sorted(positions, key=positions.get)
            order = "".join(ordered)
            gaps = np.diff([positions[name] for name in ordered])
            if order in {"AMNB", "BNMA"}:
                mean_gap = float(np.mean(gaps))
                if mean_gap > 0 and float(np.max(np.abs(gaps - mean_gap)) / mean_gap) <= 0.15:
                    result[i] = "Wenner"
                else:
                    outer_1, center, outer_2 = map(float, gaps)
                    outer_mean = (outer_1 + outer_2) / 2.0
                    outer_match = abs(outer_1 - outer_2) / max(outer_mean, 1e-12) <= 0.20
                    result[i] = "Schlumberger-like" if outer_match and center < outer_mean else "General 4-electrode"
            elif order in {"ABMN", "NMBA"}:
                ab = abs(positions["A"] - positions["B"])
                mn = abs(positions["M"] - positions["N"])
                result[i] = "Dipole-dipole" if abs(ab - mn) / max((ab + mn) / 2.0, 1e-12) <= 0.20 else "General 4-electrode"
            else:
                result[i] = "General 4-electrode"
        return result

    def reciprocal_errors(self, dataset: ElectricalDataset) -> tuple[np.ndarray, int]:
        """Calculate normal-reciprocal error from genuinely swapped dipoles.

        A reciprocal exists only when the current dipole of one record matches
        the potential dipole of another record and vice versa. Duplicate normal
        readings are intentionally not treated as reciprocals.
        """
        errors = np.full(dataset.record_count, np.nan)
        if not ({"a", "b", "m", "n"}.issubset(dataset.columns) and dataset.has("apparent_resistivity_ohm_m")):
            return errors, 0
        rho = dataset.numeric("apparent_resistivity_ohm_m")
        arrays = {name: dataset.numeric(name) for name in ("a", "b", "m", "n")}
        groups: dict[tuple[tuple[float, float], tuple[float, float]], list[int]] = defaultdict(list)
        for i in range(dataset.record_count):
            values = [arrays[name][i] for name in ("a", "b", "m", "n")]
            if not all(np.isfinite(values)):
                continue
            current = tuple(sorted((round(float(values[0]), 6), round(float(values[1]), 6))))
            potential = tuple(sorted((round(float(values[2]), 6), round(float(values[3]), 6))))
            groups[(current, potential)].append(i)

        pairs = 0
        processed: set[tuple[tuple[float, float], tuple[float, float]]] = set()
        for key, normal_indices in groups.items():
            if key in processed:
                continue
            reciprocal_key = (key[1], key[0])
            if reciprocal_key == key or reciprocal_key not in groups:
                processed.add(key)
                continue
            reciprocal_indices = groups[reciprocal_key]
            normal_valid = [index for index in normal_indices if np.isfinite(rho[index])]
            reciprocal_valid = [index for index in reciprocal_indices if np.isfinite(rho[index])]
            pair_count = min(len(normal_valid), len(reciprocal_valid))
            for normal_index, reciprocal_index in zip(normal_valid[:pair_count], reciprocal_valid[:pair_count]):
                denominator = abs(rho[normal_index]) + abs(rho[reciprocal_index])
                if denominator <= 0:
                    continue
                error = 200.0 * abs(rho[normal_index] - rho[reciprocal_index]) / denominator
                errors[normal_index] = error
                errors[reciprocal_index] = error
                pairs += 1
            processed.add(key)
            processed.add(reciprocal_key)
        return errors, pairs

    @staticmethod
    def robust_outlier_mask(values: np.ndarray, z_limit: float = 6.0, log_positive: bool = False) -> np.ndarray:
        arr = np.asarray(values, dtype=float)
        work = arr.copy()
        if log_positive:
            valid_positive = work > 0
            work[valid_positive] = np.log10(work[valid_positive])
            work[~valid_positive] = np.nan
        finite = np.isfinite(work)
        mask = np.zeros(len(work), dtype=bool)
        if np.count_nonzero(finite) < 5:
            return mask
        median = np.nanmedian(work)
        mad = np.nanmedian(np.abs(work - median))
        if not np.isfinite(mad) or mad <= 1e-12:
            return mask
        robust_z = 0.67448975 * (work - median) / mad
        mask[finite] = np.abs(robust_z[finite]) > float(z_limit)
        return mask

    @staticmethod
    def despike(values: np.ndarray, z_limit: float = 6.0, window: int = 5) -> np.ndarray:
        arr = np.asarray(values, dtype=float).copy()
        mask = ElectricalProcessingEngine.robust_outlier_mask(arr, z_limit=z_limit)
        indices = np.flatnonzero(mask)
        half = max(1, int(window) // 2)
        for index in indices:
            start = max(0, index - half)
            stop = min(len(arr), index + half + 1)
            local = arr[start:stop]
            valid = local[np.isfinite(local) & ~mask[start:stop]]
            if valid.size:
                arr[index] = float(np.median(valid))
        return arr

    @staticmethod
    def sp_drift_correct(dataset: ElectricalDataset) -> ElectricalDataset:
        output = dataset.copy()
        source_name = "sp_mv" if output.has("sp_mv") else "voltage_mv" if output.has("voltage_mv") else None
        if source_name is None or not output.has("is_base"):
            raise ValueError("SP drift correction requires SP/potential values and base/reference readings ('is_base').")
        sp = output.numeric(source_name)
        base_indices = np.flatnonzero(output.columns["is_base"].astype(bool) & np.isfinite(sp))
        if base_indices.size < 2:
            raise ValueError("At least two valid base/reference SP readings are required for drift correction.")
        drift = np.interp(np.arange(len(sp), dtype=float), base_indices.astype(float), sp[base_indices])
        drift -= drift[base_indices[0]]
        output.columns["sp_corrected_mv"] = sp - drift
        output.columns["sp_drift_mv"] = drift
        output.metadata["sp_drift_corrected"] = True
        output.metadata["sp_drift_source_field"] = source_name
        return output

    @staticmethod
    def export_rows(dataset: ElectricalDataset) -> tuple[list[str], list[list[Any]]]:
        preferred = [
            "line_id", "station", "easting", "northing", "elevation", "a", "b", "m", "n", "ab2_m", "mn2_m",
            "current_ma", "voltage_mv", "resistance_ohm", "geometry_factor_m", "apparent_resistivity_ohm_m",
            "contact_resistance_ohm", "stack_std_pct", "reciprocal_error_pct", "chargeability_mv_v", "sp_mv",
            "sp_corrected_mv", "frequency_hz", "phase_mrad", "electric_field_mv_km", "electric_field_x_mv_km",
            "electric_field_y_mv_km", "array_type", "array_type_inferred", "source_id", "repeat_id",
        ]
        headers = [name for name in preferred if dataset.has(name)]
        headers.extend(name for name in sorted(dataset.columns) if name not in headers and dataset.has(name))
        rows: list[list[Any]] = []
        for i in range(dataset.record_count):
            row: list[Any] = []
            for header in headers:
                value = dataset.columns[header][i]
                if isinstance(value, np.generic):
                    value = value.item()
                row.append(value)
            rows.append(row)
        return headers, rows
