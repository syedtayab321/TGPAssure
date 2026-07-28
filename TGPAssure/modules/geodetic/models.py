from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class RecordSchema:
    record_ids: tuple[str, ...]
    title: str
    fields: tuple[tuple[str, str], ...]

    @property
    def primary_id(self) -> str:
        return self.record_ids[0]


# Field catalogue mirrors the inspection categories visible in the supplied DC
# File Examiner screenshots.  It is deliberately a semantic catalogue rather
# than a claim about undocumented byte offsets in every vendor DC revision.
RECORD_SCHEMAS: tuple[RecordSchema, ...] = (
    RecordSchema(("00", "10"), "Header and Job", (
        ("serial_number", "Serial Number"), ("version_number", "Version Number"),
        ("file_date_time", "File Date Time"), ("angle_unit", "Angle Unit"),
        ("distance_unit", "Distance Unit"), ("job_name", "Job Name"),
        ("atmospheric_correction", "Atmospheric Correction"),
        ("curvature_refraction_corrections", "C and R Corrections"),
        ("refraction_constant", "Refraction Constant"),
    )),
    RecordSchema(("49",), "Datum", (
        ("datum_type", "Datum Type"), ("ellipsoid_radius", "Ellipsoid Radius"),
        ("ellipsoid_inverse_flattening", "Ellipsoid 1/f"),
        ("rotation_x", "Rotation X"), ("rotation_y", "Rotation Y"), ("rotation_z", "Rotation Z"),
        ("translation_x", "Translation X"), ("translation_y", "Translation Y"),
        ("translation_z", "Translation Z"), ("scale_factor", "Scale Factor"),
    )),
    RecordSchema(("50",), "Horizontal Adjust", (
        ("origin_north", "Origin North"), ("origin_east", "Origin East"),
        ("translation_north", "Trans North"), ("translation_east", "Trans East"),
        ("rotation", "Rotation"), ("scale_factor", "Scale Factor"),
    )),
    RecordSchema(("56", "57"), "Survey (Masks) and Antenna", (
        ("elevation_mask_deg", "Elevation Mask"), ("pdop_mask", "PDOP Mask"),
        ("antenna_height_m", "Antenna Height"), ("measurement_method", "Measure Method"),
    )),
    RecordSchema(("65",), "Local Ellipsoid", (
        ("local_ellipsoid_radius", "Local Ellipsoid Earth Radius"),
        ("local_ellipsoid_inverse_flattening", "Local Ellipsoid Inverse Flattening"),
    )),
    RecordSchema(("66",), "GPS Position", (
        ("point_name", "Point Name"), ("latitude_deg", "Latitude"), ("longitude_deg", "Longitude"),
        ("ellipsoid_height_m", "Ellipsoid Height at APC"), ("measurement_method", "Measurement Method"),
        ("point_classification", "Point Classification"), ("horizontal_precision_m", "Horizontal Precision"),
        ("vertical_precision_m", "Vertical Precision"),
    )),
    RecordSchema(("67",), "GPS Vector", (
        ("point_name", "Point Name"), ("delta_x_m", "Delta X"), ("delta_y_m", "Delta Y"),
        ("delta_z_m", "Delta Z"), ("measurement_method", "Measurement Method"),
        ("point_classification", "Point Classification"), ("horizontal_precision_m", "Horizontal Precision"),
        ("vertical_precision_m", "Vertical Precision"),
    )),
    RecordSchema(("68",), "Local Position", (
        ("point_name", "Point Name"), ("latitude_deg", "Latitude"), ("longitude_deg", "Longitude"),
        ("local_northing_m", "Local Northing / Y"), ("local_easting_m", "Local Easting / X"),
        ("local_ellipsoid_height_m", "Local Ellipsoid Height"),
        ("horizontal_precision_m", "Horizontal Precision"), ("vertical_precision_m", "Vertical Precision"),
        ("measurement_method", "Measurement Method"), ("point_classification", "Point Classification"),
    )),
    RecordSchema(("81",), "Vertical Adjust", (
        ("vertical_adjust_type", "Type"), ("origin_north", "Origin North"), ("origin_east", "Origin East"),
        ("constant", "Constant"), ("slope_north", "Slope North"), ("slope_east", "Slope East"),
        ("geoid", "Geoid"),
    )),
    RecordSchema(("C6",), "Quality Control 1", (
        ("min_satellites", "Min #Sats"), ("relative_dops", "Relative DOPs"), ("pdop", "PDOP"),
        ("hdop", "HDOP"), ("vdop", "VDOP"), ("rms_m", "RMS"),
        ("positions_used", "Number of Positions Used"), ("horizontal_sd_m", "Horizontal SD"),
        ("vertical_sd_m", "Vertical SD"), ("start_gps_week", "Start GPS Week"),
        ("start_gps_time_s", "Start GPS Time"), ("end_gps_week", "End GPS Week"),
        ("end_gps_time_s", "End GPS Time"), ("monitor_status", "Monitor Status"),
        ("delta_time_s", "Delta Time"),
    )),
    RecordSchema(("C8",), "Coordinate System", (
        ("system_name", "System Name"), ("zone_name", "Zone Name"), ("datum_name", "Datum Name"),
    )),
    RecordSchema(("D5",), "Local Site Settings", (
        ("project_latitude_deg", "Project Latitude"), ("project_longitude_deg", "Project Longitude"),
        ("project_height_m", "Project Height"), ("ground_scale_factor", "Ground Scale Factor"),
        ("false_northing_m", "False Northing Offset"), ("false_easting_m", "False Easting Offset"),
    )),
    RecordSchema(("E2",), "Equipment", (
        ("receiver_type", "Receiver Type"), ("receiver_serial_number", "Receiver S/N"),
        ("antenna_number", "Antenna Number"), ("antenna_index", "Antenna Index"),
        ("antenna_type", "Antenna Type"), ("antenna_serial_number", "Antenna S/N"),
        ("tape_adjustment_m", "Tape Adjustment"), ("horizontal_offset_m", "Horizontal Offset"),
        ("vertical_offset_m", "Vertical Offset"),
    )),
)

SCHEMA_BY_RECORD_ID: dict[str, RecordSchema] = {
    record_id.upper(): schema for schema in RECORD_SCHEMAS for record_id in schema.record_ids
}
FIELD_LABELS: dict[str, str] = {
    key: label for schema in RECORD_SCHEMAS for key, label in schema.fields
}


@dataclass
class DcRecord:
    record_id: str
    values: dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""
    line_number: int = 0


@dataclass
class GeodeticDataset:
    source_path: Path
    records: list[DcRecord]
    source_format: str = "dc-text"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def record_count(self) -> int:
        return len(self.records)

    def records_for(self, *record_ids: str) -> list[DcRecord]:
        wanted = {str(value).upper() for value in record_ids}
        return [record for record in self.records if record.record_id.upper() in wanted]

    def available_record_ids(self) -> set[str]:
        return {record.record_id.upper() for record in self.records}

    def field_values(self, record_ids: str | Iterable[str], field_name: str) -> np.ndarray:
        ids = (record_ids,) if isinstance(record_ids, str) else tuple(record_ids)
        values: list[Any] = []
        for record in self.records_for(*ids):
            if field_name in record.values:
                values.append(record.values[field_name])
        return np.asarray(values, dtype=object)

    def numeric_series(self, record_ids: str | Iterable[str], field_name: str) -> np.ndarray:
        values = self.field_values(record_ids, field_name)
        output = np.full(values.size, np.nan, dtype=float)
        for index, value in enumerate(values):
            try:
                output[index] = float(value)
            except (TypeError, ValueError):
                pass
        return output

    def gps_positions(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
        lon: list[float] = []
        lat: list[float] = []
        height: list[float] = []
        names: list[str] = []
        for record in self.records_for("66", "68"):
            try:
                la = float(record.values.get("latitude_deg"))
                lo = float(record.values.get("longitude_deg"))
            except (TypeError, ValueError):
                continue
            if not (-90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0):
                continue
            h_key = "ellipsoid_height_m" if record.record_id.upper() == "66" else "local_ellipsoid_height_m"
            try:
                h = float(record.values.get(h_key, 0.0))
            except (TypeError, ValueError):
                h = 0.0
            lon.append(lo); lat.append(la); height.append(h); names.append(str(record.values.get("point_name", "")))
        return (
            np.asarray(lon, dtype=float), np.asarray(lat, dtype=float), np.asarray(height, dtype=float), names
        )

    def local_positions(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
        """Return local/project coordinates when geographic coordinates are absent.

        Many survey-controller exports provide only local easting/northing after a
        site calibration.  Native 2D/3D display can still use these coordinates;
        satellite/terrain display intentionally still requires valid WGS84
        latitude/longitude.
        """
        x: list[float] = []
        y: list[float] = []
        height: list[float] = []
        names: list[str] = []
        for record in self.records_for("66", "68"):
            try:
                east = float(record.values.get("local_easting_m"))
                north = float(record.values.get("local_northing_m"))
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(east) and np.isfinite(north)):
                continue
            h_key = "ellipsoid_height_m" if record.record_id.upper() == "66" else "local_ellipsoid_height_m"
            try:
                h = float(record.values.get(h_key, 0.0))
            except (TypeError, ValueError):
                h = 0.0
            x.append(east); y.append(north); height.append(h); names.append(str(record.values.get("point_name", "")))
        return (
            np.asarray(x, dtype=float), np.asarray(y, dtype=float), np.asarray(height, dtype=float), names
        )

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.record_id] = counts.get(record.record_id, 0) + 1
        lon, lat, _height, _names = self.gps_positions()
        local_x, local_y, _local_height, _local_names = self.local_positions()
        return {
            "source_file": self.source_path.name,
            "source_path": str(self.source_path),
            "source_format": self.source_format,
            "record_count": self.record_count,
            "record_counts": counts,
            "position_count": int(lon.size),
            "local_position_count": int(local_x.size),
            "latitude_min": float(np.min(lat)) if lat.size else None,
            "latitude_max": float(np.max(lat)) if lat.size else None,
            "longitude_min": float(np.min(lon)) if lon.size else None,
            "longitude_max": float(np.max(lon)) if lon.size else None,
            "local_easting_min": float(np.min(local_x)) if local_x.size else None,
            "local_easting_max": float(np.max(local_x)) if local_x.size else None,
            "local_northing_min": float(np.min(local_y)) if local_y.size else None,
            "local_northing_max": float(np.max(local_y)) if local_y.size else None,
            **self.metadata,
        }


@dataclass
class GeodeticFinding:
    code: str
    severity: str
    title: str
    message: str
    record_id: str | None = None
    line_number: int | None = None
    observed: Any = None
    limit: Any = None
    suggested_action: str = ""


@dataclass
class GeodeticMetric:
    key: str
    label: str
    unit: str
    values: np.ndarray
    threshold: float | None = None
    direction: str = "max"  # max = values should be <= threshold; min = values should be >= threshold.

    @property
    def finite(self) -> np.ndarray:
        array = np.asarray(self.values, dtype=float)
        return array[np.isfinite(array)]


@dataclass
class GeodeticQcResult:
    profile_name: str
    status: str
    score: float
    metrics: dict[str, GeodeticMetric]
    findings: list[GeodeticFinding]
    checks: dict[str, Any] = field(default_factory=dict)
