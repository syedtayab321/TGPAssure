from __future__ import annotations

import csv
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np

from modules.magnetic.constants import RAW_TOTAL_FIELD, BASE_TOTAL_FIELD
from modules.magnetic.models import MagneticDataset


FilterMode = Literal["keep", "reject"]


@dataclass(frozen=True)
class AcquisitionSampleView:
    indices: np.ndarray
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    values: np.ndarray
    timestamps: np.ndarray
    invalid_sensor: np.ndarray
    metric_name: str
    metric_units: str


@dataclass(frozen=True)
class AcquisitionGrid:
    x_edges: np.ndarray
    y_edges: np.ndarray
    grid: np.ndarray
    metric_name: str
    metric_units: str
    stats: dict[str, Any]


class MagneticAcquisitionTools:
    """Field acquisition utilities mirrored from the EnMag Data QC workflow.

    These routines are intentionally independent of the GUI so the Magnetic QC
    module can use them for quick view, filtered exports, browser map exports,
    gap-aware track segmentation and heading/orientation diagnostics.
    """

    DEFAULT_METRIC_ALIASES = {
        "mag_nt": (RAW_TOTAL_FIELD, BASE_TOTAL_FIELD, "total_field_raw", "total_field", "mag_nt", "tmi"),
        "alt_m": ("alt_m", "altitude", "elevation"),
        "bno_heading_deg": ("bno_heading_deg", "heading", "gps_heading_deg"),
        "gps_hdop": ("gps_hdop", "hdop"),
    }

    @classmethod
    def metric_channel(cls, dataset: MagneticDataset, metric: str) -> str | None:
        aliases = cls.DEFAULT_METRIC_ALIASES.get(metric, (metric,))
        for name in aliases:
            if name in dataset.channels:
                return name
        return None

    @classmethod
    def metric_values(cls, dataset: MagneticDataset, metric: str) -> tuple[np.ndarray, str, str]:
        if metric == "alt_m":
            return np.asarray(dataset.elevation, dtype=float), "Elevation", "m"
        channel = cls.metric_channel(dataset, metric)
        if channel is None:
            return np.full(dataset.record_count, np.nan, dtype=float), metric, ""
        units = "nT" if channel in {RAW_TOTAL_FIELD, BASE_TOTAL_FIELD, "total_field", "mag_nt", "tmi"} else ""
        if "heading" in channel:
            units = "deg"
        if "hdop" in channel:
            units = ""
        return np.asarray(dataset.channels[channel], dtype=float), cls._humanize(channel), units

    @classmethod
    def sample_view(
        cls,
        dataset: MagneticDataset,
        *,
        metric: str = "mag_nt",
        include_invalid: bool = False,
        polygon: np.ndarray | None = None,
        polygon_mode: FilterMode = "keep",
    ) -> AcquisitionSampleView:
        values, label, units = cls.metric_values(dataset, metric)
        invalid = cls.invalid_sensor_mask(dataset)
        valid = dataset.valid_coordinate_mask() & np.isfinite(values)
        if not include_invalid:
            valid &= ~invalid
        if polygon is not None and len(polygon) >= 3:
            inside = point_in_polygon(np.asarray(dataset.x, dtype=float), np.asarray(dataset.y, dtype=float), polygon)
            valid &= inside if polygon_mode == "keep" else ~inside
        indices = np.flatnonzero(valid)
        return AcquisitionSampleView(
            indices=indices,
            x=np.asarray(dataset.x, dtype=float)[indices],
            y=np.asarray(dataset.y, dtype=float)[indices],
            z=np.asarray(dataset.elevation, dtype=float)[indices],
            values=values[indices],
            timestamps=dataset.timestamps[indices],
            invalid_sensor=invalid[indices],
            metric_name=label,
            metric_units=units,
        )

    @staticmethod
    def invalid_sensor_mask(dataset: MagneticDataset) -> np.ndarray:
        for key in ("sensor_validation_bad", "invalid_sensor", "sensor_bad", "gps_invalid_fix"):
            if key in dataset.quality_flags:
                return np.asarray(dataset.quality_flags[key], dtype=bool)
        return np.zeros(dataset.record_count, dtype=bool)

    @classmethod
    def parse_report(cls, dataset: MagneticDataset) -> dict[str, Any]:
        metadata_report = dict(dataset.metadata.get("parse_report") or {})
        invalid = cls.invalid_sensor_mask(dataset)
        coordinate_valid = dataset.valid_coordinate_mask()
        timestamp_valid = dataset.valid_timestamp_mask()
        gps_hdop = dataset.channels.get("gps_hdop")
        heading = dataset.channels.get("bno_heading_deg")
        report = {
            "total_records": int(metadata_report.get("total_records", dataset.record_count)),
            "gps_records": int(metadata_report.get("gps_records", metadata_report.get("source_gps_records", 0))),
            "gps_points": int(metadata_report.get("gps_points", np.count_nonzero(coordinate_valid))),
            "sensor_records": int(metadata_report.get("sensor_records", metadata_report.get("source_sensor_records", dataset.record_count))),
            "invalid_sensor_count": int(metadata_report.get("invalid_sensor_records", np.count_nonzero(invalid))),
            "invalid_sensor_ratio_pct": float(metadata_report.get("invalid_sensor_ratio_pct", 100.0 * np.count_nonzero(invalid) / max(dataset.record_count, 1))),
            "inline_event_count": int(metadata_report.get("inline_event_records", 0)),
            "inline_bad_data_event_count": int(metadata_report.get("inline_bad_data_events", 0)),
            "dropped_pre_gps_sensor_count": int(metadata_report.get("dropped_pre_gps_sensors", 0)),
            "dropped_tail_sensor_count": int(metadata_report.get("dropped_tail_sensors", 0)),
            "exportable_sample_count": int(metadata_report.get("exportable_sample_count", dataset.record_count - np.count_nonzero(invalid))),
            "valid_coordinate_pct": float(100.0 * np.count_nonzero(coordinate_valid) / max(dataset.record_count, 1)),
            "valid_timestamp_pct": float(100.0 * np.count_nonzero(timestamp_valid) / max(dataset.record_count, 1)),
            "hdop_median": float(np.nanmedian(gps_hdop)) if gps_hdop is not None and np.any(np.isfinite(gps_hdop)) else None,
            "bno_heading_available_pct": float(100.0 * np.count_nonzero(np.isfinite(heading)) / max(dataset.record_count, 1)) if heading is not None else 0.0,
        }
        movement = dataset.metadata.get("movement_summary") or {}
        for key in ("track_length_m", "median_step_m", "p95_step_m", "bounding_diagonal_m", "duration_s"):
            if key in movement:
                report[key] = movement[key]
        return report

    @classmethod
    def idw_grid(
        cls,
        view: AcquisitionSampleView,
        *,
        columns: int = 120,
        rows: int = 90,
        power: float = 2.0,
        spread: float = 1.5,
        max_points: int = 5000,
    ) -> AcquisitionGrid:
        x = view.x
        y = view.y
        z = view.values
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        x, y, z = x[finite], y[finite], z[finite]
        if z.size == 0:
            return AcquisitionGrid(np.asarray([]), np.asarray([]), np.empty((0, 0)), view.metric_name, view.metric_units, {"samples": 0})
        if z.size > max_points:
            order = np.linspace(0, z.size - 1, max_points).astype(int)
            x, y, z = x[order], y[order], z[order]
        columns = int(max(20, min(columns, 600)))
        rows = int(max(20, min(rows, 600)))
        xmin, xmax = float(np.nanmin(x)), float(np.nanmax(x))
        ymin, ymax = float(np.nanmin(y)), float(np.nanmax(y))
        if not np.isfinite([xmin, xmax, ymin, ymax]).all() or xmax <= xmin or ymax <= ymin:
            return AcquisitionGrid(np.asarray([]), np.asarray([]), np.empty((0, 0)), view.metric_name, view.metric_units, {"samples": int(z.size)})
        x_edges = np.linspace(xmin, xmax, columns)
        y_edges = np.linspace(ymin, ymax, rows)
        xi, yi = np.meshgrid(x_edges, y_edges)
        grid = np.full(xi.shape, np.nan, dtype=float)
        search_radius = spread * max((xmax - xmin) / max(columns - 1, 1), (ymax - ymin) / max(rows - 1, 1)) * 3.0
        search_radius = max(search_radius, 1e-12)
        for row in range(rows):
            dx = x[None, :] - xi[row, :, None]
            dy = y[None, :] - yi[row, :, None]
            d2 = dx * dx + dy * dy
            # Use local contributors so grid remains responsive.
            local = d2 <= search_radius * search_radius
            with np.errstate(divide="ignore", invalid="ignore"):
                weights = np.where(local, 1.0 / np.maximum(d2, 1e-24) ** (power / 2.0), 0.0)
                denom = np.sum(weights, axis=1)
                numer = np.sum(weights * z[None, :], axis=1)
                grid[row, :] = np.where(denom > 0, numer / denom, np.nan)
        return AcquisitionGrid(
            x_edges=x_edges,
            y_edges=y_edges,
            grid=grid,
            metric_name=view.metric_name,
            metric_units=view.metric_units,
            stats={
                "samples": int(z.size),
                "grid_columns": columns,
                "grid_rows": rows,
                "grid_min": float(np.nanmin(grid)) if np.any(np.isfinite(grid)) else None,
                "grid_max": float(np.nanmax(grid)) if np.any(np.isfinite(grid)) else None,
                "power": float(power),
                "spread": float(spread),
            },
        )

    @classmethod
    def segmented_track(
        cls,
        view: AcquisitionSampleView,
        *,
        gap_factor: float = 6.0,
        minimum_gap: float | None = None,
    ) -> list[np.ndarray]:
        if view.x.size < 2:
            return [np.arange(view.x.size)] if view.x.size else []
        dx = np.diff(view.x)
        dy = np.diff(view.y)
        distances = np.hypot(dx, dy)
        finite = np.isfinite(distances)
        median_step = float(np.nanmedian(distances[finite])) if np.any(finite) else 0.0
        threshold = max(minimum_gap or 0.0, gap_factor * median_step) if median_step > 0 else (minimum_gap or float("inf"))
        breaks = np.flatnonzero(distances > threshold) + 1
        return [segment for segment in np.split(np.arange(view.x.size), breaks) if segment.size]

    @classmethod
    def heading_qc(cls, dataset: MagneticDataset) -> dict[str, Any]:
        bno = dataset.channels.get("bno_heading_deg")
        gps = dataset.channels.get("gps_heading_deg")
        if gps is None:
            gps = dataset.channels.get("heading")
        if bno is None and gps is None:
            return {"available": False, "message": "No heading channels available"}
        result: dict[str, Any] = {"available": True}
        if bno is not None:
            bno = np.asarray(bno, dtype=float)
            valid = np.isfinite(bno)
            result["bno_available_pct"] = float(100.0 * np.count_nonzero(valid) / max(dataset.record_count, 1))
            if np.count_nonzero(valid) >= 2:
                jump = np.abs(((np.diff(bno[valid]) + 180.0) % 360.0) - 180.0)
                result["bno_median_jump_deg"] = float(np.nanmedian(jump)) if jump.size else 0.0
                result["bno_large_jump_count"] = int(np.count_nonzero(jump > 90.0))
        if bno is not None and gps is not None:
            gps = np.asarray(gps, dtype=float)
            both = np.isfinite(bno) & np.isfinite(gps)
            result["bno_vs_gps_samples"] = int(np.count_nonzero(both))
            if np.count_nonzero(both):
                diff = np.abs(((bno[both] - gps[both] + 180.0) % 360.0) - 180.0)
                result["bno_vs_gps_median_abs_diff_deg"] = float(np.nanmedian(diff))
                result["bno_vs_gps_p95_abs_diff_deg"] = float(np.nanpercentile(diff, 95))
        return result

    @classmethod
    def export_filtered_csv(cls, dataset: MagneticDataset, output_path: str | Path, *, metric: str = "mag_nt", include_invalid: bool = False, polygon: np.ndarray | None = None, polygon_mode: FilterMode = "keep") -> Path:
        view = cls.sample_view(dataset, metric=metric, include_invalid=include_invalid, polygon=polygon, polygon_mode=polygon_mode)
        invalid = cls.invalid_sensor_mask(dataset)
        channel_names = list(dataset.channel_names)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["index", "timestamp", "longitude_or_x", "latitude_or_y", "elevation", "selected_metric", "selected_metric_units", "invalid_sensor", *channel_names])
            for local_row, i in enumerate(view.indices):
                writer.writerow([
                    int(i),
                    str(dataset.timestamps[i]),
                    cls._safe_display(dataset.x[i]),
                    cls._safe_display(dataset.y[i]),
                    cls._safe_display(dataset.elevation[i]),
                    cls._safe_display(view.values[local_row]),
                    view.metric_units,
                    bool(invalid[i]),
                    *[cls._safe_display(dataset.channels[name][i]) for name in channel_names],
                ])
        return output

    @classmethod
    def export_leaflet_html(
        cls,
        dataset: MagneticDataset,
        output_path: str | Path,
        *,
        metric: str = "mag_nt",
        include_invalid: bool = False,
        polygon: np.ndarray | None = None,
        polygon_mode: FilterMode = "keep",
        tile_source: str = "OpenStreetMap",
    ) -> Path:
        view = cls.sample_view(dataset, metric=metric, include_invalid=include_invalid, polygon=polygon, polygon_mode=polygon_mode)
        max_points = 5000
        if view.x.size > max_points:
            take = np.linspace(0, view.x.size - 1, max_points).astype(int)
        else:
            take = np.arange(view.x.size)
        if take.size:
            values = view.values[take]
            vmin = float(np.nanpercentile(values, 2)) if np.any(np.isfinite(values)) else 0.0
            vmax = float(np.nanpercentile(values, 98)) if np.any(np.isfinite(values)) else 1.0
        else:
            vmin, vmax = 0.0, 1.0
        points = []
        for pos in take:
            x = float(view.x[pos])
            y = float(view.y[pos])
            if not np.isfinite(x) or not np.isfinite(y):
                continue
            value = float(view.values[pos]) if np.isfinite(view.values[pos]) else None
            points.append({"lat": y, "lon": x, "value": value, "invalid": bool(view.invalid_sensor[pos]), "index": int(view.indices[pos])})
        center = {"lat": float(np.nanmedian(view.y)) if view.y.size else 0.0, "lon": float(np.nanmedian(view.x)) if view.x.size else 0.0}
        polygon_json = [] if polygon is None else [[float(row[1]), float(row[0])] for row in polygon]
        stats = cls.parse_report(dataset)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        title = f"TGPAssure Magnetic Acquisition Map — {html.escape(Path(dataset.source_path).name)}"
        tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        if tile_source.lower().startswith("google"):
            tile_url = "https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}"
        doc = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>{title}</title>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>
<style>body{{margin:0;font-family:Arial,sans-serif;background:#f5f7fa;color:#102a43}}#map{{height:calc(100vh - 92px)}}.top{{padding:10px 14px;background:#102a43;color:white}}.top h2{{margin:0 0 4px 0;font-size:18px}}.stats{{font-size:12px;color:#d9e8f6}}.legend{{background:white;padding:8px;border-radius:6px;box-shadow:0 1px 8px #999;font-size:12px}}</style></head>
<body><div class='top'><h2>{title}</h2><div class='stats'>Metric: {html.escape(view.metric_name)} {html.escape(view.metric_units)} • samples: {len(points):,} • invalid sensor ratio: {stats.get('invalid_sensor_ratio_pct', 0):.2f}% • tile: {html.escape(tile_source)}</div></div><div id='map'></div>
<script>
const points = {json.dumps(points)};
const center = {json.dumps(center)};
const polygon = {json.dumps(polygon_json)};
const vmin = {json.dumps(vmin)}; const vmax = {json.dumps(vmax)};
const map = L.map('map').setView([center.lat, center.lon], 16);
L.tileLayer('{tile_url}', {{maxZoom: 22, attribution: 'Map data © contributors'}}).addTo(map);
function color(v){{ if(v===null || isNaN(v)) return '#777'; const t=Math.max(0,Math.min(1,(v-vmin)/(vmax-vmin || 1))); const r=Math.round(255*t); const b=Math.round(255*(1-t)); const g=Math.round(180*(1-Math.abs(t-0.5)*2)); return `rgb(${{r}},${{g}},${{b}})`; }}
const latlngs=[];
for (const p of points) {{
  const c = color(p.value);
  L.circleMarker([p.lat,p.lon], {{radius:p.invalid?3:4, color:p.invalid?'#111':c, fillColor:c, fillOpacity:p.invalid?0.35:0.82, weight:p.invalid?1:0}})
    .bindPopup(`Index: ${{p.index}}<br>Value: ${{p.value}}<br>Invalid sensor: ${{p.invalid}}`).addTo(map);
  latlngs.push([p.lat,p.lon]);
}}
if(latlngs.length>1) L.polyline(latlngs, {{color:'#0B6FA4', weight:2, opacity:0.65}}).addTo(map);
if(polygon.length>=3) L.polygon(polygon, {{color:'#E67E22', weight:2, fillOpacity:0.08}}).addTo(map);
if(latlngs.length) map.fitBounds(latlngs, {{padding:[20,20]}});
const legend=L.control({{position:'bottomright'}}); legend.onAdd=function(){{const div=L.DomUtil.create('div','legend');div.innerHTML=`<b>{html.escape(view.metric_name)}</b><br>${{vmin.toFixed(3)}} → ${{vmax.toFixed(3)}} {html.escape(view.metric_units)}`;return div;}}; legend.addTo(map);
</script></body></html>"""
        output.write_text(doc, encoding="utf-8")
        return output

    @staticmethod
    def _safe_display(value: Any) -> Any:
        try:
            if isinstance(value, np.datetime64):
                return str(value)
            number = float(value)
            if math.isnan(number):
                return ""
            return number
        except Exception:
            return value

    @staticmethod
    def _humanize(text: str) -> str:
        return str(text).replace("_", " ").strip().title()


def point_in_polygon(x: np.ndarray, y: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Vectorized ray-casting point-in-polygon test for XY arrays."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    polygon = np.asarray(polygon, dtype=float)
    if polygon.ndim != 2 or polygon.shape[0] < 3 or polygon.shape[1] != 2:
        return np.zeros(x.shape, dtype=bool)
    inside = np.zeros(x.shape, dtype=bool)
    xj, yj = polygon[-1]
    for xi, yi in polygon:
        crosses = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-300) + xi)
        inside ^= crosses
        xj, yj = xi, yi
    return inside
