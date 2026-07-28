from __future__ import annotations

"""Shared satellite / terrain viewer for all geophysical modules.

The widget uses Google Maps when a valid, activated Maps JavaScript API key is
available.  For field laptops or inactive keys, the 2D viewer automatically falls
back to a no-key Leaflet/Esri imagery view so imported coordinates can still be
checked against satellite context.
"""

import html
import json
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:  # QtWebEngine is shipped through PySide6 Addons in the desktop build.
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover - source-analysis/headless environments
    QWebEngineView = None  # type: ignore[assignment]


@dataclass(frozen=True)
class GeoTrack:
    name: str
    longitude: np.ndarray
    latitude: np.ndarray
    altitude_m: np.ndarray | None = None

    def payload(self, maximum_points: int = 5000) -> dict:
        lon = np.asarray(self.longitude, dtype=float).reshape(-1)
        lat = np.asarray(self.latitude, dtype=float).reshape(-1)
        if lon.size != lat.size:
            raise ValueError("Longitude and latitude arrays must contain the same number of values")
        alt = (
            np.asarray(self.altitude_m, dtype=float).reshape(-1)
            if self.altitude_m is not None
            else np.zeros(lon.size, dtype=float)
        )
        if alt.size != lon.size:
            raise ValueError("Altitude array must match longitude/latitude length")
        valid = (
            np.isfinite(lon)
            & np.isfinite(lat)
            & (lon >= -180.0)
            & (lon <= 180.0)
            & (lat >= -90.0)
            & (lat <= 90.0)
        )
        lon, lat, alt = lon[valid], lat[valid], np.nan_to_num(alt[valid], nan=0.0)
        if lon.size > maximum_points:
            idx = np.unique(np.linspace(0, lon.size - 1, maximum_points).round().astype(int))
            lon, lat, alt = lon[idx], lat[idx], alt[idx]
        return {
            "name": self.name,
            "points": [
                {"lng": float(lo), "lat": float(la), "altitude": float(al)}
                for lo, la, al in zip(lon, lat, alt)
            ],
        }


class GoogleGeospatialView(QWidget):
    """Google/Leaflet satellite and terrain context for geophysical datasets.

    API credentials are resolved at render time from the application SettingsStore
    (``google_maps_api_key``) or ``TGPASSURE_GOOGLE_MAPS_API_KEY``.  The 2D view
    can render without a Google key through a Leaflet + Esri World Imagery
    fallback.  Photorealistic 3D still requires an activated Google Maps
    JavaScript API key with billing enabled in the Google Cloud project.
    """

    MODE_2D = "2d"
    MODE_3D = "3d"
    SOURCE_AUTO = "auto"
    SOURCE_GOOGLE = "google"
    SOURCE_FREE = "free"

    def __init__(self, parent: QWidget | None = None, *, title: str = "Satellite & 3D Terrain") -> None:
        super().__init__(parent)
        self._mode = self.MODE_2D
        self._tracks: list[GeoTrack] = []
        self._title = title
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        toolbar = QFrame(self)
        toolbar.setObjectName("geoToolbar")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(5)

        title = QLabel(self._title, toolbar)
        title.setStyleSheet("font-weight:700;color:#173A52;")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row.addWidget(title)

        self.status = QLabel("Load georeferenced data.", toolbar)
        self.status.setWordWrap(False)
        self.status.setMinimumWidth(0)
        self.status.setStyleSheet("color:#5D6F7E;font-size:9px;")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        row.addWidget(self.status, 1)

        self.source_combo = QComboBox(toolbar)
        self.source_combo.addItem("Auto", self.SOURCE_AUTO)
        self.source_combo.addItem("Google", self.SOURCE_GOOGLE)
        self.source_combo.addItem("Free 2D", self.SOURCE_FREE)
        self.source_combo.setToolTip("Auto uses Google when the API key works, otherwise falls back to no-key 2D imagery.")
        self.source_combo.setFixedWidth(82)
        self.source_combo.currentIndexChanged.connect(self.render)
        row.addWidget(self.source_combo)

        self.mode_2d = QPushButton("2D", toolbar)
        self.mode_2d.setToolTip("Open the 2D satellite map")
        self.mode_3d = QPushButton("3D", toolbar)
        self.mode_3d.setToolTip("Open Google photorealistic 3D terrain when the Maps JavaScript API is active")
        self.reload_button = QPushButton("Reload", toolbar)
        self.settings_button = QPushButton("API", toolbar)
        self.settings_button.setToolTip("Open API key settings / setup guidance")
        self.mode_2d.clicked.connect(lambda: self.set_mode(self.MODE_2D))
        self.mode_3d.clicked.connect(lambda: self.set_mode(self.MODE_3D))
        self.reload_button.clicked.connect(self.render)
        self.settings_button.clicked.connect(self._open_settings_hint)
        for button in (self.mode_2d, self.mode_3d, self.reload_button, self.settings_button):
            button.setMinimumHeight(22)
            button.setMaximumHeight(25)
            row.addWidget(button)
        root.addWidget(toolbar)

        if QWebEngineView is None:
            self.web = None
            fallback = QLabel(
                "Qt WebEngine is not available in this runtime. Install/use the full PySide6 desktop build "
                "to render satellite and 3D terrain maps.",
                self,
            )
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setWordWrap(True)
            root.addWidget(fallback, 1)
        else:
            self.web = QWebEngineView(self)
            self.web.setContextMenuPolicy(Qt.NoContextMenu)
            root.addWidget(self.web, 1)
        self._sync_buttons()

    def set_tracks(self, tracks: Sequence[GeoTrack] | Iterable[GeoTrack], *, render: bool = True) -> None:
        self._tracks = [track for track in tracks]
        if render:
            self.render()

    def clear_tracks(self) -> None:
        self._tracks.clear()
        self.status.setText("Load georeferenced data.")
        if self.web is not None:
            self.web.setHtml(self._message_html("No georeferenced data loaded."))

    def set_status_message(self, message: str) -> None:
        self.status.setText(str(message))
        self.status.setToolTip(str(message))
        if self.web is not None and not self._tracks:
            self.web.setHtml(self._message_html(str(message)))

    def set_mode(self, mode: str) -> None:
        normalized = self.MODE_3D if str(mode).lower().startswith("3") else self.MODE_2D
        if normalized == self._mode and self.web is not None:
            self.render()
            return
        self._mode = normalized
        self._sync_buttons()
        self.render()

    def _sync_buttons(self) -> None:
        self.mode_2d.setEnabled(self._mode != self.MODE_2D)
        self.mode_3d.setEnabled(self._mode != self.MODE_3D)

    def _settings_store(self):
        window = self.window()
        return getattr(window, "_settings_store", None)

    def _api_key(self) -> str:
        store = self._settings_store()
        stored = ""
        if store is not None:
            try:
                stored = str(store.get("google_maps_api_key", "") or "").strip()
            except Exception:
                stored = ""
        return stored or os.environ.get("TGPASSURE_GOOGLE_MAPS_API_KEY", "").strip()

    def _source(self) -> str:
        try:
            return str(self.source_combo.currentData() or self.SOURCE_AUTO)
        except Exception:
            return self.SOURCE_AUTO

    def _open_settings_hint(self) -> None:
        window = self.window()
        opener = getattr(window, "_open_preferences", None)
        if callable(opener):
            opener()
            self.render()
            return
        QMessageBox.information(
            self,
            "Maps / Terrain Setup",
            "2D satellite can run in Auto/Free 2D mode without a Google key. Google 2D/3D requires an API key "
            "from a project where Maps JavaScript API is enabled, billing is active, and key restrictions allow "
            "this desktop/WebEngine origin. You can also set TGPASSURE_GOOGLE_MAPS_API_KEY.",
        )

    def render(self) -> None:
        if self.web is None:
            return
        payload = [track.payload() for track in self._tracks]
        payload = [track for track in payload if track["points"]]
        if not payload:
            self.status.setText("No valid WGS84 coordinates available.")
            self.web.setHtml(self._message_html("No valid geographic coordinates available."))
            return

        count = sum(len(track["points"]) for track in payload)
        key = self._api_key()
        source = self._source()

        if self._mode == self.MODE_2D:
            if source == self.SOURCE_FREE or not key:
                reason = "No-key satellite fallback" if not key else "Free 2D satellite source"
                self.status.setText(f"{count:,} points • {reason}")
                self.web.setHtml(self._html_free_2d(payload, reason), QUrl("https://tgpassure.local/"))
                return
            self.status.setText(f"{count:,} points • Google satellite with automatic fallback")
            self.web.setHtml(self._html_google_2d(key, payload), QUrl("https://tgpassure.local/"))
            return

        # Photorealistic Google 3D is a paid Google Maps JavaScript API feature.
        # In Auto/Free mode without a usable key, keep the user working by falling
        # back to the 2D satellite map instead of leaving a blank pane.
        if not key or source == self.SOURCE_FREE:
            reason = "Google 3D requires an activated Maps JavaScript API key; showing 2D satellite fallback"
            self.status.setText(f"{count:,} points • {reason}")
            self.web.setHtml(self._html_free_2d(payload, reason), QUrl("https://tgpassure.local/"))
            return
        self.status.setText(f"{count:,} points • Google photorealistic 3D terrain")
        self.web.setHtml(self._html_google_3d(key, payload), QUrl("https://tgpassure.local/"))

    @staticmethod
    def _message_html(message: str) -> str:
        return (
            "<!doctype html><html><body style='margin:0;background:#eef2f5;font-family:Arial;display:flex;"
            "align-items:center;justify-content:center;height:100vh;color:#405261'>"
            f"<div>{html.escape(message)}</div></body></html>"
        )

    @staticmethod
    def _map_center(tracks: list[dict]) -> dict[str, float]:
        pts = [p for track in tracks for p in track["points"]]
        if not pts:
            return {"lat": 0.0, "lng": 0.0, "altitude": 0.0}
        return {
            "lat": float(np.mean([p["lat"] for p in pts])),
            "lng": float(np.mean([p["lng"] for p in pts])),
            "altitude": float(np.mean([p.get("altitude", 0.0) for p in pts])),
        }

    @staticmethod
    def _leaflet_script(tracks: list[dict], reason: str = "") -> str:
        data = json.dumps(tracks, separators=(",", ":"))
        reason_json = json.dumps(reason)
        return f"""
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script>
const tracks={data};
function renderLeaflet(message){{
  const banner=document.getElementById('err');
  const note=message || {reason_json};
  if(note){{banner.style.display='block';banner.textContent=note;}}
  if(!window.L){{
    banner.style.display='block';
    banner.textContent='Fallback map library could not load. Check internet access or firewall/CDN blocking.';
    return;
  }}
  const first=tracks[0].points[0];
  const map=L.map('map',{{zoomControl:true,preferCanvas:true}}).setView([first.lat,first.lng],15);
  const imagery=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{
    maxZoom:19,
    attribution:'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
  }}).addTo(map);
  const osm=L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}});
  const topo=L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:17,attribution:'&copy; OpenTopoMap contributors'}});
  L.control.layers({{'Esri satellite':imagery,'OpenStreetMap':osm,'OpenTopo terrain':topo}},{{}},{{collapsed:true}}).addTo(map);
  const bounds=[];
  tracks.forEach((track,i)=>{{
    const path=track.points.map(p=>[p.lat,p.lng]);
    path.forEach(p=>bounds.push(p));
    if(path.length>1){{
      L.polyline(path,{{weight:2,opacity:0.95}}).addTo(map).bindTooltip(track.name || 'Track');
    }}else if(path.length===1){{
      L.circleMarker(path[0],{{radius:4,weight:2,fillOpacity:0.95}}).addTo(map).bindTooltip(track.name || 'Point');
    }}
  }});
  if(bounds.length) map.fitBounds(bounds,{{padding:[30,30],maxZoom:18}});
  window._tgpLeafletReady=true;
}}
</script>"""

    @classmethod
    def _html_free_2d(cls, tracks: list[dict], reason: str = "") -> str:
        leaflet = cls._leaflet_script(tracks, reason)
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body,#map{{height:100%;margin:0;padding:0;background:#e8eef3}}
#err{{position:absolute;z-index:9999;top:8px;left:8px;right:8px;background:rgba(255,255,255,.94);padding:6px 10px;font:12px Arial;color:#263746;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.16)}}
</style>{leaflet}</head>
<body><div id="map"></div><div id="err" style="display:none"></div><script>renderLeaflet({json.dumps(reason)});</script></body></html>"""

    @classmethod
    def _html_google_2d(cls, key: str, tracks: list[dict]) -> str:
        data = json.dumps(tracks, separators=(",", ":"))
        api = html.escape(key, quote=True)
        leaflet = cls._leaflet_script(tracks)
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body,#map{{height:100%;margin:0;padding:0;background:#e8eef3}}
#err{{position:absolute;z-index:9999;top:8px;left:8px;right:8px;background:rgba(255,255,255,.95);padding:6px 10px;font:12px Arial;color:#263746;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.16)}}
</style>{leaflet}</head>
<body><div id="map"></div><div id="err" style="display:none"></div>
<script>
const googleTracks={data};
function showGoogleError(message){{
  const e=document.getElementById('err');e.style.display='block';e.textContent=message;
}}
function initMap(){{
  window._googleMapReady=true;
  const first=googleTracks[0].points[0];
  const map=new google.maps.Map(document.getElementById('map'),{{
    center:{{lat:first.lat,lng:first.lng}},zoom:14,mapTypeId:'satellite',tilt:0,
    streetViewControl:false,mapTypeControl:true,fullscreenControl:true,scaleControl:true
  }});
  const bounds=new google.maps.LatLngBounds();
  googleTracks.forEach((track,i)=>{{
    const path=track.points.map(p=>({{lat:p.lat,lng:p.lng}}));
    path.forEach(p=>bounds.extend(p));
    if(path.length>1) new google.maps.Polyline({{path:path,map:map,geodesic:true,strokeOpacity:0.95,strokeWeight:2}});
    if(path.length===1) new google.maps.Circle({{center:path[0],radius:3,map:map,strokeWeight:2,fillOpacity:0.9}});
  }});
  if(!bounds.isEmpty()) map.fitBounds(bounds,40);
}}
window.gm_authFailure=function(){{renderLeaflet('Google Maps authentication/API activation failed. Showing no-key satellite fallback. Enable Maps JavaScript API, billing, and valid key restrictions for Google mode.');}};
function googleLoadError(){{renderLeaflet('Google Maps script did not load. Showing no-key satellite fallback.');}}
setTimeout(function(){{if(!window._googleMapReady && !window._tgpLeafletReady) renderLeaflet('Google Maps did not initialize. Showing no-key satellite fallback.');}},8000);
</script>
<script async defer src="https://maps.googleapis.com/maps/api/js?loading=async&key={api}&callback=initMap&v=weekly" onerror="googleLoadError()"></script>
</body></html>"""

    @classmethod
    def _html_google_3d(cls, key: str, tracks: list[dict]) -> str:
        data = json.dumps(tracks, separators=(",", ":"))
        api = html.escape(key, quote=True)
        center = json.dumps(cls._map_center(tracks), separators=(",", ":"))
        leaflet = cls._leaflet_script(tracks)
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body,#map{{height:100%;margin:0;padding:0;background:#e8eef3;overflow:hidden}}
#err{{position:absolute;z-index:9999;top:8px;left:8px;right:8px;background:rgba(255,255,255,.95);padding:6px 10px;font:12px Arial;color:#263746;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.16)}}
</style>{leaflet}</head>
<body><div id="map"></div><div id="err" style="display:none"></div>
<script>
const googleTracks={data};
const center={center};
function googleLoadError(){{renderLeaflet('Google Maps 3D script did not load. Showing no-key 2D satellite fallback.');}}
window.gm_authFailure=function(){{renderLeaflet('Google Maps authentication/API activation failed. Showing no-key 2D satellite fallback. Enable Maps JavaScript API, billing, and 3D Maps access for Google 3D.');}};
async function init3D(){{
  try{{
    window._googleMapReady=true;
    const lib=await google.maps.importLibrary('maps3d');
    const Map3DElement=lib.Map3DElement;
    const Polyline3DElement=lib.Polyline3DElement;
    const map=new Map3DElement({{center:center,range:8000,tilt:62,heading:0,mode:'HYBRID'}});
    document.getElementById('map').append(map);
    googleTracks.forEach(track=>{{
      if(track.points.length<2) return;
      const path=track.points.map(p=>({{lat:p.lat,lng:p.lng,altitude:p.altitude||0}}));
      const line=new Polyline3DElement({{path:path,strokeWidth:4,altitudeMode:'RELATIVE_TO_GROUND',drawsOccludedSegments:true}});
      map.append(line);
    }});
  }}catch(err){{
    renderLeaflet('Google 3D terrain failed: '+err+'. Showing no-key 2D satellite fallback.');
  }}
}}
setTimeout(function(){{if(!window._googleMapReady && !window._tgpLeafletReady) renderLeaflet('Google 3D did not initialize. Showing no-key 2D satellite fallback.');}},9000);
</script>
<script async defer src="https://maps.googleapis.com/maps/api/js?loading=async&key={api}&libraries=maps3d&callback=init3D&v=weekly" onerror="googleLoadError()"></script>
</body></html>"""
