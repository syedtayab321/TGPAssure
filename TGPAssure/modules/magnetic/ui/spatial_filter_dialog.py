from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from modules.magnetic.enmag_qc.spatial import SpatialFilterDefinition, apply_polygon_filter, polygon_inside_mask

_SPATIAL_FILTER_STYLE = """
QDialog {
    background:#F4F6F8;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:8pt;
    color:#1F2933;
}
QLabel#instructionLabel {
    color:#263745;
    font-weight:600;
}
QLabel#counterLabel {
    color:#174A7C;
    font-weight:600;
    background:#EAF2FB;
    border:1px solid #BBD0E4;
    border-radius:4px;
    padding:4px 8px;
}
QPushButton {
    min-height:24px;
    padding:3px 10px;
    border-radius:4px;
    border:1px solid #AEB9C5;
    background:#EFF3F7;
}
QPushButton:hover { background:#E1EAF5; }
QPushButton#applyButton { background:#DDF4E5; border-color:#79BE91; font-weight:600; }
QPushButton#applyButton:hover { background:#CFEEDB; }
QPushButton#undoButton { background:#E7F0FF; border-color:#8BB1DE; }
QPushButton#resetButton { background:#F5EBDD; border-color:#D4B57E; }
QPushButton#closeButton { background:#F0F2F4; }
QRadioButton { spacing:5px; color:#263745; }
"""


class _SpatialPointCloudCanvas(QWidget):
    polygon_changed = Signal(object)

    def __init__(self, x: np.ndarray, y: np.ndarray, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(720, 440)
        self.setMouseTracking(True)
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        finite = np.isfinite(self.x) & np.isfinite(self.y)
        self._finite_indices = np.flatnonzero(finite)
        if self._finite_indices.size:
            xmin = float(np.nanmin(self.x[finite])); xmax = float(np.nanmax(self.x[finite]))
            ymin = float(np.nanmin(self.y[finite])); ymax = float(np.nanmax(self.y[finite]))
        else:
            xmin, xmax, ymin, ymax = 0.0, 1.0, 0.0, 1.0
        if xmax <= xmin: xmax = xmin + 1.0
        if ymax <= ymin: ymax = ymin + 1.0
        px = (xmax - xmin) * 0.04; py = (ymax - ymin) * 0.04
        self.bounds = (xmin-px, xmax+px, ymin-py, ymax+py)
        self.vertices: list[tuple[float, float]] = []
        self.hover_world: tuple[float, float] | None = None
        self._point_image: QImage | None = None
        self._point_image_size: tuple[int, int] | None = None

    def set_vertices(self, vertices: np.ndarray | list[tuple[float, float]]) -> None:
        arr = np.asarray(vertices, dtype=float)
        self.vertices = [(float(v[0]), float(v[1])) for v in arr] if arr.ndim == 2 and arr.shape[1] == 2 else []
        self.polygon_changed.emit(np.asarray(self.vertices, dtype=float))
        self.update()

    def undo_point(self) -> None:
        if self.vertices:
            self.vertices.pop()
            self.polygon_changed.emit(np.asarray(self.vertices, dtype=float))
            self.update()

    def reset_polygon(self) -> None:
        self.vertices.clear()
        self.hover_world = None
        self.polygon_changed.emit(np.empty((0,2), dtype=float))
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(14.0, 14.0, max(1.0, self.width()-28.0), max(1.0, self.height()-28.0))

    def world_to_screen(self, x: np.ndarray | float, y: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
        rect = self.plot_rect(); xmin,xmax,ymin,ymax = self.bounds
        sx = rect.left() + (np.asarray(x)-xmin)/max(xmax-xmin,1e-15)*rect.width()
        sy = rect.top() + (ymax-np.asarray(y))/max(ymax-ymin,1e-15)*rect.height()
        return sx, sy

    def screen_to_world(self, p: QPointF) -> tuple[float,float]:
        rect = self.plot_rect(); xmin,xmax,ymin,ymax = self.bounds
        x = xmin + (p.x()-rect.left())/max(rect.width(),1.0)*(xmax-xmin)
        y = ymax - (p.y()-rect.top())/max(rect.height(),1.0)*(ymax-ymin)
        return float(x), float(y)

    def _build_point_image(self) -> QImage:
        rect = self.plot_rect()
        width = max(1, int(rect.width())); height = max(1, int(rect.height()))
        rgba = np.full((height, width, 4), 255, dtype=np.uint8)
        rgba[..., 0:3] = 252
        if self._finite_indices.size:
            sx, sy = self.world_to_screen(self.x[self._finite_indices], self.y[self._finite_indices])
            px = np.clip(np.rint(sx-rect.left()).astype(np.int64), 0, width-1)
            py = np.clip(np.rint(sy-rect.top()).astype(np.int64), 0, height-1)
            for ox, oy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
                xx = np.clip(px+ox,0,width-1); yy=np.clip(py+oy,0,height-1)
                rgba[yy,xx,0] = 28; rgba[yy,xx,1] = 96; rgba[yy,xx,2] = 168; rgba[yy,xx,3] = 255
        rgba = np.ascontiguousarray(rgba)
        return QImage(rgba.data,width,height,width*4,QImage.Format.Format_RGBA8888).copy()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255,255,255))
        painter.fillRect(rect, QColor(250,252,255))
        rect = self.plot_rect()
        size = (max(1,int(rect.width())),max(1,int(rect.height())))
        if self._point_image is None or self._point_image_size != size:
            self._point_image = self._build_point_image(); self._point_image_size=size
        painter.drawImage(rect,self._point_image)
        if self.vertices:
            sx,sy=self.world_to_screen(np.asarray([v[0] for v in self.vertices]),np.asarray([v[1] for v in self.vertices]))
            painter.setPen(QPen(QColor(225,70,45),2))
            pts=[QPointF(float(a),float(b)) for a,b in zip(sx,sy)]
            for a,b in zip(pts[:-1],pts[1:]): painter.drawLine(a,b)
            if len(pts)>=3: painter.drawLine(pts[-1],pts[0])
            if self.hover_world is not None:
                hx,hy=self.world_to_screen(self.hover_world[0],self.hover_world[1])
                painter.setPen(QPen(QColor(225,70,45,160),1,Qt.PenStyle.DashLine))
                painter.drawLine(pts[-1],QPointF(float(hx),float(hy)))
            painter.setBrush(QColor(255,255,255)); painter.setPen(QPen(QColor(180,45,30),1))
            for pt in pts: painter.drawEllipse(pt,3.5,3.5)
        painter.setPen(QPen(QColor(215,215,215),1)); painter.drawRect(rect)

    def mousePressEvent(self,event:QMouseEvent)->None:
        if event.button()==Qt.MouseButton.LeftButton and self.plot_rect().contains(event.position()):
            self.vertices.append(self.screen_to_world(event.position()))
            self.polygon_changed.emit(np.asarray(self.vertices,dtype=float)); self.update(); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event:QMouseEvent)->None:
        self.hover_world=self.screen_to_world(event.position()) if self.plot_rect().contains(event.position()) else None
        self.update(); super().mouseMoveEvent(event)


class SpatialFilterDialog(QDialog):
    filter_applied = Signal(object, str)
    filters_reset = Signal()

    def __init__(
        self,
        x: np.ndarray,
        y: np.ndarray,
        base_visible_mask: np.ndarray,
        *,
        existing_filter: SpatialFilterDefinition | None = None,
        filter_number: int = 1,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Spatial Filter")
        self.setModal(True)
        self.resize(980, 660)
        self.setStyleSheet(_SPATIAL_FILTER_STYLE)
        self.x=np.asarray(x,dtype=float); self.y=np.asarray(y,dtype=float)
        self.base_visible=np.asarray(base_visible_mask,dtype=bool)
        self.coordinate_total = int(np.count_nonzero(np.isfinite(self.x) & np.isfinite(self.y)))
        self.filter_number=max(1,int(filter_number))
        self._applied_mask: np.ndarray | None = None

        root=QVBoxLayout(self); root.setContentsMargins(14,14,14,14); root.setSpacing(10)
        top=QHBoxLayout(); top.setSpacing(10)
        instruction = QLabel("Click points to draw a polygon over the raw coordinate cloud.")
        instruction.setObjectName("instructionLabel")
        top.addWidget(instruction,1)
        self.ignore_radio=QRadioButton("Ignore selection"); self.keep_radio=QRadioButton("Keep only selection")
        group=QButtonGroup(self); group.setExclusive(True); group.addButton(self.ignore_radio); group.addButton(self.keep_radio)
        self.ignore_radio.setChecked(True)
        top.addWidget(self.ignore_radio); top.addWidget(self.keep_radio)
        self.apply_btn=QPushButton("Apply Selection"); self.apply_btn.setObjectName("applyButton")
        self.undo_btn=QPushButton("Undo Point"); self.undo_btn.setObjectName("undoButton")
        self.reset_btn=QPushButton("Reset Filters"); self.reset_btn.setObjectName("resetButton")
        top.addWidget(self.apply_btn); top.addWidget(self.undo_btn); top.addWidget(self.reset_btn)
        root.addLayout(top)

        self.canvas=_SpatialPointCloudCanvas(self.x,self.y,self); root.addWidget(self.canvas,1)
        bottom=QHBoxLayout(); bottom.setSpacing(10); self.counter=QLabel("none | visible: 0/0"); self.counter.setObjectName("counterLabel"); bottom.addWidget(self.counter,1)
        close_btn=QPushButton("Close"); close_btn.setObjectName("closeButton"); close_btn.clicked.connect(self.accept); bottom.addWidget(close_btn); root.addLayout(bottom)

        if existing_filter is not None:
            self.canvas.set_vertices(existing_filter.vertices)
            (self.keep_radio if existing_filter.mode=="keep" else self.ignore_radio).setChecked(True)
            self._applied_mask=existing_filter.mask(self.x,self.y)

        self.canvas.polygon_changed.connect(self._update_counter)
        self.ignore_radio.toggled.connect(self._update_counter)
        self.keep_radio.toggled.connect(self._update_counter)
        self.apply_btn.clicked.connect(self._apply)
        self.undo_btn.clicked.connect(self.canvas.undo_point)
        self.reset_btn.clicked.connect(self._reset)
        self._update_counter()

    def _mode(self)->str:
        return "keep" if self.keep_radio.isChecked() else "ignore"

    def _candidate_mask(self)->np.ndarray | None:
        vertices=np.asarray(self.canvas.vertices,dtype=float)
        if vertices.ndim!=2 or vertices.shape[0]<3:
            return None
        inside=polygon_inside_mask(self.x,self.y,vertices)
        return inside if self._mode()=="keep" else ~inside

    def _update_counter(self,*_args)->None:
        candidate=self._candidate_mask()
        can_apply = candidate is not None
        if candidate is None:
            effective=self.base_visible if self._applied_mask is None else (self.base_visible & self._applied_mask)
            name="none" if self._applied_mask is None else f"{self._mode().title()} selection {self.filter_number}"
        else:
            effective=self.base_visible & candidate
            name=f"{self._mode().title()} selection {self.filter_number} (preview)"
        self.apply_btn.setEnabled(can_apply)
        self.counter.setText(f"{name} | visible: {int(np.count_nonzero(effective))}/{self.coordinate_total}")

    def _apply(self)->None:
        vertices=np.asarray(self.canvas.vertices,dtype=float)
        if vertices.ndim!=2 or vertices.shape[0]<3:
            self.counter.setText("Polygon needs at least 3 points | selection not applied")
            return
        mode=self._mode()
        inside=polygon_inside_mask(self.x,self.y,vertices)
        mask=inside if mode=="keep" else ~inside
        name=("Keep" if mode=="keep" else "Ignore")+f" selection {self.filter_number}"
        self._applied_mask=mask
        self.filter_applied.emit(SpatialFilterDefinition(name=name,vertices=vertices.copy(),mode=mode),name)
        self._update_counter()
        self.accept()

    def _reset(self)->None:
        self._applied_mask=None
        self.canvas.reset_polygon()
        self.filters_reset.emit()
        self._update_counter()
