from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QPushButton, QWidget

from modules.magnetic.enmag_qc.models import ColorRange, EnMagQcData, GridResult
from modules.magnetic.enmag_qc.spatial import CoordinateIndex

try:  # Optional at source level; declared as a project dependency for packaged builds.
    from pyproj import Transformer
except Exception:  # pragma: no cover - exercised only in stripped developer environments
    Transformer = None


_PALETTES: dict[str, tuple[tuple[float, tuple[int, int, int]], ...]] = {
    "Spectral": (
        (0.00, (20, 70, 210)),
        (0.20, (0, 165, 245)),
        (0.42, (28, 205, 155)),
        (0.58, (85, 220, 105)),
        (0.73, (245, 225, 75)),
        (0.86, (255, 145, 40)),
        (1.00, (225, 20, 55)),
    ),
    "Jet": (
        (0.00, (0, 45, 220)),
        (0.20, (0, 185, 255)),
        (0.40, (40, 210, 120)),
        (0.60, (245, 235, 70)),
        (0.80, (255, 135, 25)),
        (1.00, (230, 0, 55)),
    ),
    "Viridis": (
        (0.00, (68, 1, 84)),
        (0.25, (59, 82, 139)),
        (0.50, (33, 145, 140)),
        (0.75, (94, 201, 98)),
        (1.00, (253, 231, 37)),
    ),
    "Gray": (
        (0.00, (35, 35, 35)),
        (1.00, (245, 245, 245)),
    ),
}


def palette_rgba(values_01: np.ndarray, name: str = "Spectral") -> np.ndarray:
    values = np.clip(np.asarray(values_01, dtype=float), 0.0, 1.0)
    stops = _PALETTES.get(name, _PALETTES["Spectral"])
    xp = np.asarray([s[0] for s in stops], dtype=float)
    rgb = np.asarray([s[1] for s in stops], dtype=float)
    flat = values.ravel()
    out = np.empty((flat.size, 4), dtype=np.uint8)
    out[:, 0] = np.interp(flat, xp, rgb[:, 0]).astype(np.uint8)
    out[:, 1] = np.interp(flat, xp, rgb[:, 1]).astype(np.uint8)
    out[:, 2] = np.interp(flat, xp, rgb[:, 2]).astype(np.uint8)
    out[:, 3] = 255
    return out.reshape(values.shape + (4,))


def solid_palette_color(fraction: float, name: str = "Spectral") -> QColor:
    rgba = palette_rgba(np.asarray([fraction]), name).reshape(-1, 4)[0]
    return QColor(int(rgba[0]), int(rgba[1]), int(rgba[2]), 255)


class EnMagColorBar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.setMaximumHeight(34)
        self._range: ColorRange | None = None
        self._palette = "Spectral"

    def set_state(self, color_range: ColorRange | None, palette: str = "Spectral") -> None:
        self._range = color_range
        self._palette = palette
        self.update()

    @staticmethod
    def _fmt(value: float, unit: str) -> str:
        if unit == "deg":
            return f"{value:.1f} {unit}"
        if abs(value) >= 1000:
            return f"{value:.3f} {unit}".strip()
        return f"{value:.4g} {unit}".strip()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window().color())
        state = self._range
        if state is None:
            p.setPen(QColor(95, 95, 95))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No color scale")
            return

        left_label_w = 112
        right_label_w = 112
        bar = QRectF(left_label_w, 7, max(20, self.width() - left_label_w - right_label_w), 15)
        p.setPen(QColor(45, 45, 45))
        p.drawText(QRectF(0, 0, left_label_w - 8, 30), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._fmt(state.data_min, state.unit))
        p.drawText(QRectF(self.width() - right_label_w + 8, 0, right_label_w - 8, 30), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._fmt(state.data_max, state.unit))

        span = max(state.data_max - state.data_min, 1e-15)
        lo_frac = float(np.clip((state.scale_min - state.data_min) / span, 0.0, 1.0))
        hi_frac = float(np.clip((state.scale_max - state.data_min) / span, 0.0, 1.0))
        lo_x = bar.left() + lo_frac * bar.width()
        hi_x = bar.left() + hi_frac * bar.width()

        if lo_x > bar.left():
            p.fillRect(QRectF(bar.left(), bar.top(), lo_x - bar.left(), bar.height()), solid_palette_color(0.0, self._palette))
        grad_left = max(bar.left(), min(lo_x, bar.right()))
        grad_right = max(grad_left + 1.0, min(hi_x, bar.right()))
        width = max(1, int(math.ceil(grad_right - grad_left)))
        fractions = np.linspace(0.0, 1.0, width, dtype=float)
        rgba = palette_rgba(fractions, self._palette).reshape(1, width, 4)
        image = QImage(np.ascontiguousarray(rgba).data, width, 1, width * 4, QImage.Format.Format_RGBA8888).copy()
        p.drawImage(QRectF(grad_left, bar.top(), grad_right - grad_left, bar.height()), image)
        if hi_x < bar.right():
            p.fillRect(QRectF(max(hi_x, bar.left()), bar.top(), bar.right() - max(hi_x, bar.left()), bar.height()), solid_palette_color(1.0, self._palette))
            clip_label = "Robust clip" if state.mode.lower().startswith("robust") else "Manual clip"
            if bar.right() - max(hi_x, bar.left()) > 70:
                p.setPen(QColor(55, 55, 55))
                p.drawText(QRectF(max(hi_x, bar.left()), bar.top(), bar.right() - max(hi_x, bar.left()), bar.height()), Qt.AlignmentFlag.AlignCenter, clip_label)
        if lo_x > bar.left() and lo_x - bar.left() > 60:
            p.setPen(QColor(245, 245, 245))
            p.drawText(QRectF(bar.left(), bar.top(), lo_x - bar.left(), bar.height()), Qt.AlignmentFlag.AlignCenter, "Low clip")

        p.setPen(QPen(QColor(170, 170, 170), 1))
        p.drawRect(bar)
        if state.data_min < state.scale_min < state.data_max:
            p.setPen(QPen(QColor(250, 250, 250), 1))
            p.drawLine(QPointF(lo_x, bar.top()), QPointF(lo_x, bar.bottom()))
        if state.data_min < state.scale_max < state.data_max:
            p.setPen(QPen(QColor(250, 250, 250), 1))
            p.drawLine(QPointF(hi_x, bar.top()), QPointF(hi_x, bar.bottom()))


class EnMagPreviewCanvas(QWidget):
    hover_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(540, 320)
        self._data: EnMagQcData | None = None
        self._grid_result: GridResult | None = None
        self._grid_image: QImage | None = None
        self._color_range: ColorRange | None = None
        self._palette_name = "Spectral"
        self._opacity = 1.0
        self._mode = "Grid"
        self._pan_enabled = True
        self._view_bounds = (0.0, 1.0, 0.0, 1.0)
        self._drag_origin: QPointF | None = None
        self._drag_view: tuple[float, float, float, float] | None = None
        self._visible_mask: np.ndarray | None = None
        self._coordinate_index: CoordinateIndex | None = None
        self._hover_grid_label = "Magnetic Field"
        self._hover_grid_unit = "nT"
        self._hover_values: np.ndarray | None = None
        self._hover_circular = False
        self._transformer = None

    def set_data(self, data: EnMagQcData | None) -> None:
        self._data = data
        self._grid_result = None
        self._grid_image = None
        self._color_range = None
        self._visible_mask = None
        self._coordinate_index = None
        self._transformer = None
        if data is not None:
            self.fit_to_data()
            self._prepare_transformer()
        self.update()

    def _prepare_transformer(self) -> None:
        if self._data is None or self._data.is_geographic or Transformer is None or not self._data.crs:
            return
        try:
            self._transformer = Transformer.from_crs(self._data.crs, "EPSG:4326", always_xy=True)
        except Exception:
            self._transformer = None

    def set_visible_mask(self, mask: np.ndarray | None) -> None:
        self._visible_mask = None if mask is None else np.asarray(mask, dtype=bool).copy()
        if self._data is None:
            self._coordinate_index = None
        else:
            if self._visible_mask is None:
                m = np.isfinite(self._data.x) & np.isfinite(self._data.y)
            else:
                m = self._visible_mask & np.isfinite(self._data.x) & np.isfinite(self._data.y)
            self._coordinate_index = CoordinateIndex(
                self._data.x[m],
                self._data.y[m],
                geographic=self._data.is_geographic,
                coordinate_units=self._data.coordinate_units,
            )
            # CoordinateIndex indices are local to the masked subset.  Keep the
            # source mapping for direct raw-sample access after a query.
            self._hover_source_indices = np.flatnonzero(m)
        self.update()

    def set_render(
        self,
        grid_result: GridResult | None,
        color_range: ColorRange | None,
        *,
        palette_name: str = "Spectral",
        mode: str = "Grid",
        grid_label: str = "Magnetic Field",
        grid_values: np.ndarray | None = None,
    ) -> None:
        self._grid_result = grid_result
        self._color_range = color_range
        self._palette_name = palette_name
        self._mode = mode
        self._hover_grid_label = grid_label
        self._hover_grid_unit = color_range.unit if color_range is not None else ""
        self._hover_values = None if grid_values is None else np.asarray(grid_values, dtype=float)
        self._hover_circular = "heading" in grid_label.lower()
        self._grid_image = self._make_grid_image(grid_result, color_range) if grid_result is not None and color_range is not None else None
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = float(np.clip(opacity, 0.0, 1.0))
        self.update()

    def set_pan_enabled(self, enabled: bool) -> None:
        self._pan_enabled = bool(enabled)
        self.setCursor(Qt.CursorShape.OpenHandCursor if enabled else Qt.CursorShape.ArrowCursor)

    def fit_to_data(self) -> None:
        if self._data is None:
            self._view_bounds = (0.0, 1.0, 0.0, 1.0)
            return
        finite = np.isfinite(self._data.x) & np.isfinite(self._data.y)
        if not np.any(finite):
            self._view_bounds = (0.0, 1.0, 0.0, 1.0)
            return
        xmin = float(np.nanmin(self._data.x[finite]))
        xmax = float(np.nanmax(self._data.x[finite]))
        ymin = float(np.nanmin(self._data.y[finite]))
        ymax = float(np.nanmax(self._data.y[finite]))
        if xmax <= xmin:
            xmax = xmin + 1.0
        if ymax <= ymin:
            ymax = ymin + 1.0
        px = (xmax - xmin) * 0.08
        py = (ymax - ymin) * 0.08
        self._view_bounds = (xmin - px, xmax + px, ymin - py, ymax + py)
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(0.0, 0.0, max(1.0, float(self.width())), max(1.0, float(self.height())))

    def world_to_screen(self, x: float | np.ndarray, y: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rect = self._plot_rect()
        xmin, xmax, ymin, ymax = self._view_bounds
        xx = rect.left() + (np.asarray(x, dtype=float) - xmin) / max(xmax - xmin, 1e-15) * rect.width()
        yy = rect.top() + (ymax - np.asarray(y, dtype=float)) / max(ymax - ymin, 1e-15) * rect.height()
        return xx, yy

    def screen_to_world(self, point: QPointF) -> tuple[float, float]:
        rect = self._plot_rect()
        xmin, xmax, ymin, ymax = self._view_bounds
        x = xmin + (point.x() - rect.left()) / max(rect.width(), 1.0) * (xmax - xmin)
        y = ymax - (point.y() - rect.top()) / max(rect.height(), 1.0) * (ymax - ymin)
        return float(x), float(y)

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        factor = max(0.1, float(factor))
        rect = self._plot_rect()
        if anchor is None:
            anchor = rect.center()
        wx, wy = self.screen_to_world(anchor)
        xmin, xmax, ymin, ymax = self._view_bounds
        new_w = (xmax - xmin) / factor
        new_h = (ymax - ymin) / factor
        fx = float(np.clip((anchor.x() - rect.left()) / max(rect.width(), 1.0), 0.0, 1.0))
        fy = float(np.clip((anchor.y() - rect.top()) / max(rect.height(), 1.0), 0.0, 1.0))
        new_xmin = wx - fx * new_w
        new_xmax = new_xmin + new_w
        new_ymax = wy + fy * new_h
        new_ymin = new_ymax - new_h
        self._view_bounds = (new_xmin, new_xmax, new_ymin, new_ymax)
        self.update()

    def _make_grid_image(self, result: GridResult, color_range: ColorRange) -> QImage:
        values = np.asarray(result.values, dtype=float)
        valid = np.isfinite(values)
        frac = (values - color_range.scale_min) / max(color_range.scale_max - color_range.scale_min, 1e-15)
        rgba = palette_rgba(np.nan_to_num(frac, nan=0.0), self._palette_name)
        rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
        rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
        rows, cols = values.shape
        return QImage(rgba.data, cols, rows, cols * 4, QImage.Format.Format_RGBA8888).copy()

    def _draw_grid(self, painter: QPainter) -> None:
        if self._grid_image is None or self._grid_result is None:
            return
        xmin, xmax, ymin, ymax = self._grid_result.bounds
        left, top = self.world_to_screen(xmin, ymax)
        right, bottom = self.world_to_screen(xmax, ymin)
        target = QRectF(float(left), float(top), float(right - left), float(bottom - top))
        painter.save()
        painter.setOpacity(self._opacity)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, self._grid_image)
        painter.restore()

    def _draw_points(self, painter: QPainter) -> None:
        if self._data is None:
            return
        mask = self._visible_mask
        if mask is None:
            mask = np.isfinite(self._data.x) & np.isfinite(self._data.y)
        indices = np.flatnonzero(mask)
        if indices.size == 0:
            return
        # Drawing every point remains practical at the target 25k-50k scale;
        # cap only pathological displays while preserving the actual survey shape.
        step = max(1, int(math.ceil(indices.size / 80_000)))
        indices = indices[::step]
        sx, sy = self.world_to_screen(self._data.x[indices], self._data.y[indices])
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(30, 48, 58, 210), 0.55))
        painter.setBrush(QColor(244, 204, 64, 230))
        radius = 2.0 if self._mode.lower() != "points" else 2.8
        for px, py in zip(sx, sy):
            painter.drawEllipse(QPointF(float(px), float(py)), radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        if self._data is None:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select a magnetic log file to begin")
            return
        if self._mode.lower() == "points":
            self._draw_points(painter)
        else:
            self._draw_grid(painter)
            self._draw_points(painter)
        painter.setPen(QPen(QColor(225, 225, 225), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pan_enabled:
            self._drag_origin = event.position()
            self._drag_view = self._view_bounds
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and self._drag_view is not None and event.buttons() & Qt.MouseButton.LeftButton:
            dx = event.position().x() - self._drag_origin.x()
            dy = event.position().y() - self._drag_origin.y()
            xmin, xmax, ymin, ymax = self._drag_view
            wx_per_px = (xmax - xmin) / max(self.width(), 1)
            wy_per_px = (ymax - ymin) / max(self.height(), 1)
            self._view_bounds = (xmin - dx * wx_per_px, xmax - dx * wx_per_px, ymin + dy * wy_per_px, ymax + dy * wy_per_px)
            self.update()
            event.accept()
            return
        self._emit_hover(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            self._drag_origin = None
            self._drag_view = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._pan_enabled else Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.zoom_by(1.22 if event.angleDelta().y() > 0 else 1.0 / 1.22, event.position())
        event.accept()

    def leaveEvent(self, event) -> None:
        self.hover_changed.emit("Move over the map to inspect grid and nearest point values.")
        super().leaveEvent(event)

    def _grid_value_at(self, x: float, y: float) -> float | None:
        result = self._grid_result
        if result is None:
            return None
        xmin, xmax, ymin, ymax = result.bounds
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            return None
        col = (x - xmin) / max(xmax - xmin, 1e-15) * (result.cols - 1)
        row = (ymax - y) / max(ymax - ymin, 1e-15) * (result.rows - 1)
        c0 = int(np.floor(col)); c1 = min(c0 + 1, result.cols - 1)
        r0 = int(np.floor(row)); r1 = min(r0 + 1, result.rows - 1)
        fc = col - c0; fr = row - r0
        vals = np.asarray([result.values[r0, c0], result.values[r0, c1], result.values[r1, c0], result.values[r1, c1]], dtype=float)
        weights = np.asarray([(1-fr)*(1-fc), (1-fr)*fc, fr*(1-fc), fr*fc], dtype=float)
        finite = np.isfinite(vals)
        if not np.any(finite):
            return None
        valid_vals = vals[finite]
        valid_weights = weights[finite]
        if self._hover_circular:
            radians = np.deg2rad(np.mod(valid_vals, 360.0))
            s = np.sum(np.sin(radians) * valid_weights)
            c = np.sum(np.cos(radians) * valid_weights)
            return float(np.mod(np.rad2deg(np.arctan2(s, c)), 360.0))
        return float(np.sum(valid_vals * valid_weights) / max(np.sum(valid_weights), 1e-15))

    def _to_lat_lon(self, x: float, y: float) -> tuple[float, float] | None:
        if self._data is None:
            return None
        if self._data.is_geographic:
            return float(y), float(x)
        if self._transformer is not None:
            try:
                lon, lat = self._transformer.transform(x, y)
                return float(lat), float(lon)
            except Exception:
                return None
        return None

    def _emit_hover(self, point: QPointF) -> None:
        if self._data is None or self._coordinate_index is None:
            return
        wx, wy = self.screen_to_world(point)
        query = self._coordinate_index.query(wx, wy)
        if query is None:
            return
        local_index, distance, distance_unit = query
        source_map = getattr(self, "_hover_source_indices", None)
        if source_map is None or local_index < 0 or local_index >= source_map.size:
            return
        idx = int(source_map[local_index])
        grid_value = self._grid_value_at(wx, wy)
        latlon = self._to_lat_lon(wx, wy)
        if latlon is None:
            location = f"x/y: {wx:.3f}, {wy:.3f}"
        else:
            lat, lon = latlon
            location = f"lat/lon: {lat:.6f}, {lon:.6f}"
        unit = self._hover_grid_unit or ""
        grid_text = "n/a" if grid_value is None else f"{grid_value:.3f} {unit}".strip()
        point_mag = self._data.magnetic_nt[idx]
        mag_text = "n/a" if not np.isfinite(point_mag) else f"{point_mag:.3f} nT"
        alt = self._data.altitude_m[idx]
        alt_text = "n/a" if not np.isfinite(alt) else f"{alt:.1f} m"
        self.hover_changed.emit(
            f"Grid {self._hover_grid_label}: {grid_text} | {location} | "
            f"Point Magnetic Field: {mag_text} | alt: {alt_text} | d: {distance:.1f} {distance_unit}"
        )


class EnMagCanvasContainer(QWidget):
    def __init__(self, canvas: EnMagPreviewCanvas, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self.canvas.setParent(self)
        self.zoom_in = QPushButton("+", self)
        self.zoom_out = QPushButton("−", self)
        for button in (self.zoom_in, self.zoom_out):
            button.setObjectName("enmagZoomButton")
            button.setFixedSize(32, 32)
            button.raise_()
        self.zoom_in.clicked.connect(lambda: self.canvas.zoom_by(1.25))
        self.zoom_out.clicked.connect(lambda: self.canvas.zoom_by(1.0 / 1.25))

    def resizeEvent(self, event) -> None:
        self.canvas.setGeometry(self.rect())
        self.zoom_in.move(16, 18)
        self.zoom_out.move(16, 55)
        self.zoom_in.raise_(); self.zoom_out.raise_()
        super().resizeEvent(event)
