from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from modules.magnetic.models import MagneticBoundary


class MagneticBoundaryReader:
    """Read magnetic survey boundaries without silently relabelling coordinates.

    KML/KMZ coordinates are always geographic WGS84 longitude/latitude, so
    they are returned as EPSG:4326.  A caller-supplied CRS is only used for
    formats whose coordinates do not carry an inherent CRS (CSV/TXT/XYZ).
    """

    def read(self, path: str | Path, crs: str | None = None) -> MagneticBoundary:
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix == ".kmz":
            with zipfile.ZipFile(source) as archive:
                kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
                if not kml_names:
                    raise ValueError("KMZ contains no KML document")
                data = archive.read(kml_names[0])
            vertices = self._read_kml_bytes(data)
            return MagneticBoundary(vertices, "EPSG:4326", source.stem)
        if suffix == ".kml":
            vertices = self._read_kml_bytes(source.read_bytes())
            return MagneticBoundary(vertices, "EPSG:4326", source.stem)
        if suffix in {".json", ".geojson"}:
            payload = json.loads(source.read_text(encoding="utf-8"))
            geometry = payload.get("geometry", payload)
            if payload.get("type") == "FeatureCollection":
                if not payload.get("features"):
                    raise ValueError("GeoJSON FeatureCollection contains no features")
                geometry = payload["features"][0]["geometry"]
            if payload.get("type") == "Feature":
                geometry = payload["geometry"]
            coordinates = geometry["coordinates"]
            if geometry["type"] == "MultiPolygon":
                coordinates = coordinates[0]
            vertices = np.asarray(coordinates[0], dtype=float)[:, :2]
            # RFC 7946 GeoJSON coordinates are WGS84 lon/lat unless a legacy
            # producer explicitly documents something else.
            return MagneticBoundary(vertices, crs or "EPSG:4326", source.stem)
        if suffix in {".csv", ".txt", ".xyz"}:
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            vertices = []
            for row in rows:
                try:
                    vertices.append((float(row[0]), float(row[1])))
                except (ValueError, IndexError):
                    continue
            return MagneticBoundary(np.asarray(vertices), crs, source.stem)
        raise ValueError(f"Unsupported magnetic boundary format: {suffix}")

    @staticmethod
    def _read_kml_bytes(data: bytes) -> np.ndarray:
        root = ElementTree.fromstring(data)
        coordinates = root.findall(".//{*}Polygon//{*}coordinates")
        if not coordinates:
            coordinates = root.findall(".//{*}LinearRing/{*}coordinates")
        if not coordinates or not coordinates[0].text:
            raise ValueError("KML contains no polygon coordinates")
        vertices = []
        for token in coordinates[0].text.replace("\n", " ").split():
            parts = token.split(",")
            if len(parts) >= 2:
                vertices.append((float(parts[0]), float(parts[1])))
        return np.asarray(vertices, dtype=float)
