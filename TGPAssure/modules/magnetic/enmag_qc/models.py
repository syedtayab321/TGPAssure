from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from modules.magnetic.constants import RAW_TOTAL_FIELD
from modules.magnetic.models import MagneticDataset


DEFAULT_MAG_MIN_NT = 1_000.0
DEFAULT_MAG_MAX_NT = 100_000.0


def _first_channel(dataset: MagneticDataset, candidates: Iterable[str]) -> tuple[str, np.ndarray]:
    for name in candidates:
        if name in dataset.channels:
            return name, np.asarray(dataset.channels[name], dtype=float)
    if not dataset.channels:
        raise ValueError("Magnetic dataset contains no numeric channels")
    name = next(iter(dataset.channels))
    return name, np.asarray(dataset.channels[name], dtype=float)


@dataclass(slots=True)
class EnMagQcData:
    """Flat, UI-oriented view of a :class:`MagneticDataset`.

    The application-level ``MagneticDataset`` remains the source of truth.  This
    adapter only normalises the channels needed by the EnMag-style QC screen and
    keeps source counters (raw log rows / GPS records) separate from the number
    of georeferenced magnetic samples.
    """

    source_path: Path
    timestamps: np.ndarray
    longitude_or_x: np.ndarray
    latitude_or_y: np.ndarray
    altitude_m: np.ndarray
    magnetic_nt: np.ndarray
    heading_deg: np.ndarray
    gps_fix_quality: np.ndarray
    line_id: np.ndarray
    station_id: np.ndarray
    source_name: np.ndarray
    sensor_bad: np.ndarray
    gps_bad: np.ndarray
    raw_records: int
    gps_records: int
    crs: str | None
    coordinate_units: str
    channel_name: str = RAW_TOTAL_FIELD
    mag_min_nt: float = DEFAULT_MAG_MIN_NT
    mag_max_nt: float = DEFAULT_MAG_MAX_NT
    extra_channels: dict[str, np.ndarray] = field(default_factory=dict)

    @classmethod
    def from_dataset(cls, dataset: MagneticDataset, *, channel_name: str | None = None) -> "EnMagQcData":
        preferred = [channel_name] if channel_name else []
        preferred += [RAW_TOTAL_FIELD, "mag", "tmi", "total_field", "magnetic_field"]
        actual_channel, magnetic = _first_channel(dataset, [name for name in preferred if name])
        n = dataset.record_count
        heading = np.asarray(dataset.channels.get("heading", np.full(n, np.nan)), dtype=float)
        if not np.any(np.isfinite(heading)):
            bno = np.asarray(dataset.channels.get("bno_heading_deg", np.full(n, np.nan)), dtype=float)
            gps = np.asarray(dataset.channels.get("gps_heading_deg", np.full(n, np.nan)), dtype=float)
            heading = gps.copy()
            heading[np.isfinite(bno)] = bno[np.isfinite(bno)]
        gps_quality = np.asarray(dataset.channels.get("gps_quality", np.ones(n)), dtype=float)
        sensor_bad = np.asarray(dataset.quality_flags.get("sensor_validation_bad", np.zeros(n, dtype=bool)), dtype=bool)
        gps_bad = np.asarray(dataset.quality_flags.get("gps_invalid_fix", np.zeros(n, dtype=bool)), dtype=bool)

        report = dataset.metadata.get("parse_report", {}) if isinstance(dataset.metadata, dict) else {}
        raw_records = int(
            report.get("total_records")
            or dataset.metadata.get("source_raw_records", 0)
            or dataset.metadata.get("source_records", 0)
            or n
        )
        gps_records = int(
            report.get("gps_points")
            or report.get("gps_records")
            or dataset.metadata.get("source_gps_records", 0)
            or np.count_nonzero(np.isfinite(dataset.x) & np.isfinite(dataset.y))
        )

        extra: dict[str, np.ndarray] = {}
        for name, values in dataset.channels.items():
            arr = np.asarray(values, dtype=float)
            if arr.size == n:
                extra[name] = arr
        extra.setdefault("elevation", np.asarray(dataset.elevation, dtype=float))
        extra.setdefault("heading", heading)

        return cls(
            source_path=Path(dataset.source_path),
            timestamps=np.asarray(dataset.timestamps, dtype="datetime64[ms]"),
            longitude_or_x=np.asarray(dataset.x, dtype=float),
            latitude_or_y=np.asarray(dataset.y, dtype=float),
            altitude_m=np.asarray(dataset.elevation, dtype=float),
            magnetic_nt=magnetic,
            heading_deg=heading,
            gps_fix_quality=gps_quality,
            line_id=np.asarray(dataset.line_id, dtype=object),
            station_id=np.asarray(dataset.station_id, dtype=object),
            source_name=np.full(n, Path(dataset.source_path).name, dtype=object),
            sensor_bad=sensor_bad,
            gps_bad=gps_bad,
            raw_records=max(raw_records, n),
            gps_records=max(gps_records, 0),
            crs=dataset.crs,
            coordinate_units=dataset.coordinate_units or "",
            channel_name=actual_channel,
            extra_channels=extra,
        )

    @property
    def sample_count(self) -> int:
        return int(self.magnetic_nt.size)

    @property
    def x(self) -> np.ndarray:
        return self.longitude_or_x

    @property
    def y(self) -> np.ndarray:
        return self.latitude_or_y

    @property
    def is_geographic(self) -> bool:
        crs = (self.crs or "").upper().replace(" ", "")
        units = (self.coordinate_units or "").lower()
        if crs in {"EPSG:4326", "4326", "WGS84", "WGS-84"}:
            return True
        if "degree" in units:
            finite = np.isfinite(self.x) & np.isfinite(self.y)
            if np.any(finite):
                return bool(np.nanmax(np.abs(self.x[finite])) <= 180.0 and np.nanmax(np.abs(self.y[finite])) <= 90.0)
        return False

    def values_for_grid_type(self, grid_type: str) -> tuple[np.ndarray, str, str, bool]:
        """Return values, human label, unit and circular-data flag."""
        key = (grid_type or "Mag").strip().lower()
        if key in {"heading", "bno heading", "sensor heading"}:
            return self.heading_deg, "BNO Heading", "deg", True
        if key in {"elevation", "altitude", "gps elevation"}:
            return self.altitude_m, "Elevation", "m", False
        if key in self.extra_channels:
            return np.asarray(self.extra_channels[key], dtype=float), grid_type, "nT", False
        return self.magnetic_nt, "Magnetic Field", "nT", False

    def hard_displayable_mask(self, values: np.ndarray | None = None) -> np.ndarray:
        """Rows that can physically be drawn.

        ``Include Invalid Samples`` can re-include quality-rejected samples, but
        cannot make missing coordinates or NaN channel values drawable.
        """
        vals = self.magnetic_nt if values is None else np.asarray(values, dtype=float)
        return np.isfinite(self.x) & np.isfinite(self.y) & np.isfinite(vals)

    def quality_valid_mask(self, values: np.ndarray | None = None) -> np.ndarray:
        vals = self.magnetic_nt if values is None else np.asarray(values, dtype=float)
        mask = self.hard_displayable_mask(vals)
        mask &= ~self.sensor_bad
        mask &= ~self.gps_bad
        # Validity is a record-level concept in the reference tool.  A bad or
        # physically implausible magnetic reading remains invalid even when the
        # user is previewing Heading or Elevation.  ``Include Invalid Samples``
        # can deliberately re-include those rows.
        mask &= np.isfinite(self.magnetic_nt)
        mask &= self.magnetic_nt >= self.mag_min_nt
        mask &= self.magnetic_nt <= self.mag_max_nt
        return mask

    def visible_mask(
        self,
        *,
        values: np.ndarray | None = None,
        include_invalid: bool = False,
        spatial_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        vals = self.magnetic_nt if values is None else np.asarray(values, dtype=float)
        mask = self.hard_displayable_mask(vals) if include_invalid else self.quality_valid_mask(vals)
        if spatial_mask is not None:
            spatial = np.asarray(spatial_mask, dtype=bool)
            if spatial.size != mask.size:
                raise ValueError("Spatial filter mask length does not match the dataset")
            mask &= spatial
        return mask


@dataclass(slots=True)
class GridResult:
    values: np.ndarray
    bounds: tuple[float, float, float, float]
    x_coordinates: np.ndarray
    y_coordinates: np.ndarray
    nearest_source_index: np.ndarray
    method: str

    @property
    def rows(self) -> int:
        return int(self.values.shape[0])

    @property
    def cols(self) -> int:
        return int(self.values.shape[1])


@dataclass(slots=True, frozen=True)
class ColorRange:
    data_min: float
    data_max: float
    scale_min: float
    scale_max: float
    mode: str
    unit: str

    @property
    def has_low_clip(self) -> bool:
        return self.data_min < self.scale_min

    @property
    def has_high_clip(self) -> bool:
        return self.data_max > self.scale_max
