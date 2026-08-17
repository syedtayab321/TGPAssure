from __future__ import annotations

import math
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from core.visualization.palette_library import DEFAULT_PALETTE, palette_hex


class SeismicGeometryMap(QWidget):
    """Plan-view seismic geometry viewer with physically correct XY aspect ratio."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._geometry: dict[str, np.ndarray] = {}
        self._palette_name = DEFAULT_PALETTE
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(6)
        bar = QFrame(); bar.setObjectName("geometryMapBar")
        row = QHBoxLayout(bar); row.setContentsMargins(8,6,8,6)
        self.sources = QCheckBox("Sources"); self.sources.setChecked(True)
        self.receivers = QCheckBox("Receivers"); self.receivers.setChecked(True)
        self.midpoints = QCheckBox("Midpoints/CDP"); self.midpoints.setChecked(True)
        self.connect = QCheckBox("Connect midpoint path"); self.connect.setChecked(True)
        fit = QPushButton("Fit Map")
        for w in (self.sources,self.receivers,self.midpoints,self.connect): w.toggled.connect(self.render)
        fit.clicked.connect(self.fit)
        row.addWidget(self.sources); row.addWidget(self.receivers); row.addWidget(self.midpoints); row.addWidget(self.connect); row.addStretch(1); row.addWidget(fit)
        root.addWidget(bar)
        self.plot = pg.PlotWidget(background="#07131F")
        self.plot.setLabel("bottom","X / Easting"); self.plot.setLabel("left","Y / Northing")
        self.plot.showGrid(x=True,y=True,alpha=0.15); self.plot.setAspectLocked(True, ratio=1)
        self.plot.addLegend(offset=(10,10)); root.addWidget(self.plot,1)
        self.stats = QLabel("Load seismic data to display geometry."); self.stats.setWordWrap(True); self.stats.setObjectName("geometryMapStats"); root.addWidget(self.stats)

    @staticmethod
    def _valid_xy(x, y):
        x=np.asarray(x,dtype=float); y=np.asarray(y,dtype=float); m=np.isfinite(x)&np.isfinite(y)&~((x==0)&(y==0)); return x[m],y[m],m

    def set_palette(self, palette_name: str) -> None:
        self._palette_name = str(palette_name or DEFAULT_PALETTE)
        self.render()

    def set_geometry(self, geometry: dict[str,np.ndarray]) -> None:
        self._geometry = geometry or {}; self.render(); self.fit()

    def clear(self) -> None:
        self._geometry={}; self.plot.clear(); self.stats.setText("Load seismic data to display geometry.")

    def render(self) -> None:
        self.plot.clear(); g=self._geometry
        if not g: return
        sx,sy,_=self._valid_xy(g.get("source_x",[]),g.get("source_y",[]))
        rx,ry,_=self._valid_xy(g.get("receiver_x",[]),g.get("receiver_y",[]))
        mx,my,_=self._valid_xy(g.get("midpoint_x",[]),g.get("midpoint_y",[]))
        if self.sources.isChecked() and sx.size: self.plot.plot(sx,sy,pen=None,symbol="t",symbolSize=6,symbolBrush=palette_hex(self._palette_name, 0.18),name="Sources")
        if self.receivers.isChecked() and rx.size: self.plot.plot(rx,ry,pen=None,symbol="o",symbolSize=5,symbolBrush=palette_hex(self._palette_name, 0.50),name="Receivers")
        if self.midpoints.isChecked() and mx.size:
            pen=pg.mkPen(palette_hex(self._palette_name, 0.82),width=1) if self.connect.isChecked() else None
            self.plot.plot(mx,my,pen=pen,symbol="s",symbolSize=4,symbolBrush=palette_hex(self._palette_name, 0.82),name="Midpoints/CDP")
        self._update_stats(mx,my)

    def _update_stats(self,x,y):
        if x.size<1: self.stats.setText("No valid XY midpoint/CDP geometry found."); return
        dx=np.diff(x); dy=np.diff(y); dist=np.hypot(dx,dy); valid=dist>0
        path=float(np.sum(dist[valid])) if np.any(valid) else 0.0
        med=float(np.median(dist[valid])) if np.any(valid) else 0.0
        if np.any(valid):
            az=(np.degrees(np.arctan2(dx[valid],dy[valid]))+360.0)%360.0
            rad=np.radians(az); mean_az=(math.degrees(math.atan2(np.mean(np.sin(rad)),np.mean(np.cos(rad))))+360)%360
        else: mean_az=0.0
        self.stats.setText(f"Valid map points: {x.size:,}   |   X range: {np.min(x):.3f}–{np.max(x):.3f}   |   Y range: {np.min(y):.3f}–{np.max(y):.3f}   |   Path length: {path:,.2f} coordinate units   |   Median station spacing: {med:,.2f}   |   Mean path azimuth: {mean_az:.1f}°")

    def fit(self) -> None:
        self.plot.enableAutoRange(x=True,y=True); self.plot.autoRange(padding=0.04)
