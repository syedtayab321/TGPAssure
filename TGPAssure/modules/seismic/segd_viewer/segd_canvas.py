from __future__ import annotations

import numpy as np
from typing import Optional, Tuple, Any, Dict, List
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QThreadPool, QRunnable, QObject
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPixmap, QImage, QMouseEvent, QWheelEvent, QKeyEvent
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem, QWidget, QFrame

from core.infrastructure.job_manager import JobManager
from core.infrastructure.job import Job, JobSpec, CancellationToken
from modules.seismic.segd_viewer.trace_window_loader import TraceWindowLoader
from modules.seismic.segd_viewer.decimator import Decimator
from modules.seismic.segd_viewer.gain_stage import GainStage
from modules.seismic.segd_viewer.rasterizer import Rasterizer
from core.domain.colormap_registry import ColormapRegistry


class RenderJob(Job):
    def __init__(self, canvas: SegdCanvas, viewport: Dict[str, Any]) -> None:
        spec = JobSpec(
            job_type="segd_render",
            module="segd_viewer",
            priority=5,
            payload_json=str(viewport)
        )
        super().__init__(spec)
        self.canvas = canvas
        self.viewport = viewport

    def run(self, context: Any, cancel_token: CancellationToken) -> Dict[str, Any]:
        return self.canvas._do_render(self.viewport, cancel_token)


class SegdCanvas(QGraphicsView):
    viewport_changed = Signal()
    pick_created = Signal(dict)
    measurement_updated = Signal(float, float)

    MODE_PAN = "pan"
    MODE_SELECT = "select"
    MODE_PICK = "pick"
    MODE_MEASURE = "measure"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        self._mode = self.MODE_PAN
        self._zoom_x = 1.0
        self._zoom_y = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._trace_start = 0
        self._trace_end = 100
        self._sample_start = 0
        self._sample_end = 500
        self._total_traces = 0
        self._total_samples = 0

        self._last_viewport = None
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._on_render_timeout)

        self._pan_start = None
        self._pan_origin = None
        self._measure_start = None
        self._measure_end = None
        self._measure_item = None

        self._loader: Optional[TraceWindowLoader] = None
        self._decimator = Decimator()
        self._gain_stage = GainStage()
        self._rasterizer = Rasterizer()
        self._colormap_registry = ColormapRegistry()
        self._job_manager: Optional[JobManager] = None

        self._current_colormap = "seismic"
        self._current_display_mode = Rasterizer.DISPLAY_VARIABLE_DENSITY
        self._current_gain_mode = GainStage.MODE_AGC
        self._current_gain_params = {"window_length": 100}
        self._current_clip_percentile = 99.0
        self._selected_channels = [0]

        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setFrameShape(QFrame.NoFrame)

    def initialize(self, loader: TraceWindowLoader, job_manager: JobManager) -> None:
        self._loader = loader
        self._job_manager = job_manager
        self._total_traces = loader.get_trace_count()
        self._total_samples = loader.get_sample_count()
        self._trace_end = min(100, self._total_traces)
        self._sample_end = min(500, self._total_samples)
        self._request_render()

    def set_colormap(self, colormap_name: str) -> None:
        self._current_colormap = colormap_name
        self._request_render()

    def set_display_mode(self, mode: str) -> None:
        self._current_display_mode = mode
        self._request_render()

    def set_gain_mode(self, mode: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._current_gain_mode = mode
        if params:
            self._current_gain_params.update(params)
        self._request_render()

    def set_clip_percentile(self, percentile: float) -> None:
        self._current_clip_percentile = percentile
        self._request_render()

    def set_selected_channels(self, channels: List[int]) -> None:
        self._selected_channels = channels
        self._request_render()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if mode == self.MODE_PAN:
            self.setCursor(Qt.OpenHandCursor)
        elif mode == self.MODE_SELECT:
            self.setCursor(Qt.CrossCursor)
        elif mode == self.MODE_PICK:
            self.setCursor(Qt.PointingHandCursor)
        elif mode == self.MODE_MEASURE:
            self.setCursor(Qt.CrossCursor)
            self._measure_start = None
            self._measure_end = None
            self._remove_measure_item()

    def zoom_to_fit(self) -> None:
        if self._total_traces > 0 and self._total_samples > 0:
            self._trace_start = 0
            self._trace_end = self._total_traces
            self._sample_start = 0
            self._sample_end = self._total_samples
            self._zoom_x = 1.0
            self._zoom_y = 1.0
            self._offset_x = 0.0
            self._offset_y = 0.0
            self._request_render()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self._zoom_y *= factor
            self._zoom_y = max(0.01, min(10.0, self._zoom_y))
            self._request_render()
        elif event.modifiers() & Qt.ShiftModifier:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self._zoom_x *= factor
            self._zoom_x = max(0.01, min(10.0, self._zoom_x))
            self._request_render()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton:
            self._mode = self.MODE_PAN
            self._pan_start = event.position()
            self._pan_origin = QPointF(self._offset_x, self._offset_y)
            self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.LeftButton:
            if self._mode == self.MODE_PAN:
                self._pan_start = event.position()
                self._pan_origin = QPointF(self._offset_x, self._offset_y)
                self.setCursor(Qt.ClosedHandCursor)
            elif self._mode == self.MODE_PICK:
                self._handle_pick(event)
            elif self._mode == self.MODE_MEASURE:
                self._handle_measure_start(event)
            elif self._mode == self.MODE_SELECT:
                self._handle_select(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan_start is not None and (event.buttons() & Qt.LeftButton or event.buttons() & Qt.MiddleButton):
            delta = event.position() - self._pan_start
            self._offset_x = self._pan_origin.x() + delta.x() / self._zoom_x
            self._offset_y = self._pan_origin.y() + delta.y() / self._zoom_y
            self._request_render()
        elif self._mode == self.MODE_MEASURE and self._measure_start is not None:
            self._handle_measure_update(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton:
            self._pan_start = None
            self._pan_origin = None
            self.setCursor(Qt.OpenHandCursor if self._mode == self.MODE_PAN else Qt.ArrowCursor)
        elif event.button() == Qt.LeftButton and self._mode == self.MODE_PAN:
            self._pan_start = None
            self._pan_origin = None
            self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space:
            self._mode = self.MODE_PAN
            self.setCursor(Qt.OpenHandCursor)
        elif event.key() == Qt.Key_F:
            self.zoom_to_fit()
        super().keyPressEvent(event)

    def _handle_pick(self, event: QMouseEvent) -> None:
        pos = self.mapToScene(event.position().toPoint())
        trace_idx = int(pos.x() / 2) if self._pixmap_item.pixmap().width() > 0 else 0
        sample_idx = int(pos.y() / 2) if self._pixmap_item.pixmap().height() > 0 else 0

        if 0 <= trace_idx < self._total_traces and 0 <= sample_idx < self._total_samples:
            pick_data = {
                "trace_index": trace_idx,
                "sample_index": sample_idx,
                "trace_start": self._trace_start,
                "trace_end": self._trace_end,
                "sample_start": self._sample_start,
                "sample_end": self._sample_end,
                "zoom_x": self._zoom_x,
                "zoom_y": self._zoom_y,
                "offset_x": self._offset_x,
                "offset_y": self._offset_y
            }
            self.pick_created.emit(pick_data)

    def _handle_measure_start(self, event: QMouseEvent) -> None:
        pos = self.mapToScene(event.position().toPoint())
        self._measure_start = pos
        self._measure_end = pos
        self._remove_measure_item()

    def _handle_measure_update(self, event: QMouseEvent) -> None:
        pos = self.mapToScene(event.position().toPoint())
        self._measure_end = pos
        self._update_measure_item()

    def _handle_select(self, event: QMouseEvent) -> None:
        pass

    def _remove_measure_item(self) -> None:
        if self._measure_item:
            self._scene.removeItem(self._measure_item)
            self._measure_item = None

    def _update_measure_item(self) -> None:
        self._remove_measure_item()
        if self._measure_start is None or self._measure_end is None:
            return

        dx = self._measure_end.x() - self._measure_start.x()
        dy = self._measure_end.y() - self._measure_start.y()
        time_delta = dy / 2.0
        amplitude_delta = dx

        self.measurement_updated.emit(time_delta, amplitude_delta)

        pen = QPen(QColor(255, 200, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)

        rect = QRectF(self._measure_start, self._measure_end)
        self._measure_item = self._scene.addRect(rect, pen)
        self._measure_item.setZValue(100)

        if abs(dx) > 5 and abs(dy) > 5:
            text_item = self._scene.addText(
                f"dt: {abs(time_delta):.2f} ms, da: {abs(amplitude_delta):.2f}",
                self.font()
            )
            text_item.setDefaultTextColor(QColor(255, 200, 0))
            text_item.setPos(rect.center())
            text_item.setZValue(101)
            self._measure_item = text_item

    def _request_render(self) -> None:
        self._render_timer.stop()
        self._render_timer.start(50)

    def _on_render_timeout(self) -> None:
        if self._loader is None or self._job_manager is None:
            return

        viewport = self._calculate_viewport()
        if self._last_viewport == viewport:
            return

        self._last_viewport = viewport
        job = RenderJob(self, viewport)
        self._job_manager.submit(job)

    def _calculate_viewport(self) -> Dict[str, Any]:
        view_rect = self.viewport().rect()
        center = self.mapToScene(view_rect.center())

        trace_width = 2 * self._zoom_x
        sample_height = 2 * self._zoom_y

        trace_start = max(0, int(center.x() / trace_width - view_rect.width() / (2 * trace_width)))
        trace_end = min(self._total_traces, int(center.x() / trace_width + view_rect.width() / (2 * trace_width) + 1))

        sample_start = max(0, int(center.y() / sample_height - view_rect.height() / (2 * sample_height)))
        sample_end = min(self._total_samples, int(center.y() / sample_height + view_rect.height() / (2 * sample_height) + 1))

        self._trace_start = trace_start
        self._trace_end = trace_end
        self._sample_start = sample_start
        self._sample_end = sample_end

        return {
            "trace_start": trace_start,
            "trace_end": trace_end,
            "sample_start": sample_start,
            "sample_end": sample_end,
            "zoom_x": self._zoom_x,
            "zoom_y": self._zoom_y,
            "offset_x": self._offset_x,
            "offset_y": self._offset_y,
            "viewport_width": view_rect.width(),
            "viewport_height": view_rect.height(),
            "colormap": self._current_colormap,
            "display_mode": self._current_display_mode,
            "gain_mode": self._current_gain_mode,
            "gain_params": self._current_gain_params,
            "clip_percentile": self._current_clip_percentile,
            "channels": self._selected_channels
        }

    def _do_render(self, viewport: Dict[str, Any], cancel_token: CancellationToken) -> Dict[str, Any]:
        if cancel_token.is_cancelled():
            return {"cancelled": True}

        trace_start = viewport["trace_start"]
        trace_end = viewport["trace_end"]
        sample_start = viewport["sample_start"]
        sample_end = viewport["sample_end"]
        viewport_width = viewport["viewport_width"]
        viewport_height = viewport["viewport_height"]

        if trace_end - trace_start <= 0 or sample_end - sample_start <= 0:
            return {"cancelled": True}

        if cancel_token.is_cancelled():
            return {"cancelled": True}

        data = self._loader.read((trace_start, trace_end), (sample_start, sample_end), viewport["channels"][0])

        if data.size == 0:
            return {"cancelled": True}

        if cancel_token.is_cancelled():
            return {"cancelled": True}

        if data.ndim == 3 and data.shape[1] == 1:
            data = data[:, 0, :]

        reduced = self._decimator.reduce_to_width(data, viewport_width, viewport_height)

        if cancel_token.is_cancelled():
            return {"cancelled": True}

        gained = self._gain_stage.apply(reduced, viewport["gain_mode"], viewport["gain_params"])

        if cancel_token.is_cancelled():
            return {"cancelled": True}

        colormap = self._colormap_registry.get(viewport["colormap"])
        if colormap is None:
            colormap = self._colormap_registry.get_default()

        qimage = self._rasterizer.to_qimage(gained, viewport["display_mode"], colormap, viewport_width, viewport_height)

        return {"qimage": qimage}

    def _apply_render_result(self, result: Dict[str, Any]) -> None:
        if "cancelled" in result and result["cancelled"]:
            return

        qimage = result.get("qimage")
        if qimage is not None and not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            self._pixmap_item.setPixmap(pixmap)
            self._scene.setSceneRect(QRectF(pixmap.rect()))
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self.viewport_changed.emit()