from __future__ import annotations

import logging
import re
import uuid
from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QResizeEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from modules.seismic.visualization.models import (
    DisplayMode,
    GainSettings,
    InterpretationObject,
    InterpretationPoint,
    QcTraceFlag,
    SectionData,
)
from modules.seismic.visualization.processing import apply_gain, robust_scale, snap_sample
from modules.seismic.visualization.seismic_attributes import (
    ATTRIBUTE_NAMES,
    AttributeParameters,
    attribute_display_range,
    compute_attribute,
)
from ui.theme.petrel_theme import FONT_FAMILY, FONT_SIZE_CAPTION, FONT_SIZE_SMALL
from core.visualization.palette_library import DEFAULT_PALETTE, palette_rgb_array
from ui.widgets.palette_colorbar import PaletteColorBar

# Axis/tick text is deliberately smaller than the app's normal 9pt scale: a
# seismic section can carry 200+ trace columns, so oversized tick labels are
# the single biggest contributor to a "messy" looking plot.
_AXIS_FONT = QFont(FONT_FAMILY, FONT_SIZE_SMALL)
_TICK_FONT = QFont(FONT_FAMILY, FONT_SIZE_CAPTION)


logger = logging.getLogger(__name__)


class Seismic2DView(QWidget):
    cursor_changed = Signal(int, int, float, float)
    interpretations_changed = Signal()
    measurement_completed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section: SectionData | None = None
        self._processed = np.empty((0, 0), dtype=np.float32)
        self._display_data = np.empty((0, 0), dtype=np.float32)
        self._attribute_mode = "amplitude"
        self._attribute_parameters = AttributeParameters()
        self._display_mode: DisplayMode = "wiggle_density"
        self._label_mode = "auto"
        self._gain_settings = GainSettings()
        self._qc_flags: list[QcTraceFlag] = []
        self._interpretations: list[InterpretationObject] = []
        self._picking_kind: str | None = None
        self._picking_name = ""
        self._picking_color = "#00E5FF"
        self._active_object_id: str | None = None
        self._measurement_start: InterpretationPoint | None = None
        self._overlay_items: list[pg.GraphicsObject] = []
        self._wiggle_item: pg.PlotCurveItem | None = None
        self._image_item: pg.ImageItem | None = None
        self._qc_item: pg.PlotCurveItem | None = None
        self._noise_item: pg.ImageItem | None = None
        self._noise_trace_indices = np.empty(0, dtype=np.int64)
        self._noise_scores = np.empty(0, dtype=np.float32)
        self._noise_overlay_visible = True
        self._palette_name = DEFAULT_PALETTE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot_widget = pg.PlotWidget(background="#07131F")
        self.plot_widget.setAntialiasing(False)
        self.plot = self.plot_widget.getPlotItem()
        self.plot.setLabel("left", "Two-way time", units="ms")
        self.plot.setLabel("bottom", "Displayed trace")
        self.plot.showAxis("top")
        self.plot.showGrid(x=True, y=True, alpha=0.10)
        self._view_box = self.plot.getViewBox()
        self._view_box.invertY(True)
        self._view_box.setMouseMode(pg.ViewBox.PanMode)
        self._view_box.setDefaultPadding(0.01)
        self._view_box.disableAutoRange()
        for axis_name in ("left", "bottom", "top"):
            axis = self.plot.getAxis(axis_name)
            axis.setTickFont(_TICK_FONT)
            axis.setStyle(tickTextOffset=4)
            axis.setPen(pg.mkPen("#4C6478"))
            axis.setTextPen(pg.mkPen("#B8C9D6"))
        self.plot.getAxis("top").setHeight(38)
        self.plot.getAxis("top").setStyle(
            tickTextOffset=4,
            autoExpandTextSpace=False,
            hideOverlappingLabels=True,
            showValues=True,
        )
        self.plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.plot.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        layout.addWidget(self.plot_widget, 1)
        self.colorbar = PaletteColorBar(self)
        self.colorbar.set_state(-1.0, 1.0, self._palette_name, unit="", label="Amplitude / attribute value")
        layout.addWidget(self.colorbar)

    @property
    def section(self) -> SectionData | None:
        return self._section

    @property
    def processed_amplitudes(self) -> np.ndarray:
        return self._processed

    @property
    def display_attribute(self) -> str:
        return self._attribute_mode

    @property
    def display_data(self) -> np.ndarray:
        return self._display_data

    @property
    def interpretations(self) -> list[InterpretationObject]:
        return self._interpretations

    def set_scene(
        self,
        section: SectionData,
        gain_settings: GainSettings,
        display_mode: str,
        label_mode: str,
        qc_flags: Iterable[QcTraceFlag],
        interpretations: list[InterpretationObject],
        noise_trace_indices: np.ndarray,
        noise_scores: np.ndarray,
        noise_overlay_visible: bool,
    ) -> None:
        if display_mode not in {"wiggle", "variable_density", "wiggle_density"}:
            display_mode = "wiggle_density"
        self._section = section
        self._gain_settings = gain_settings
        self._display_mode = display_mode
        self._label_mode = label_mode
        self._qc_flags = list(qc_flags)
        self._interpretations = interpretations
        self._noise_trace_indices = np.asarray(noise_trace_indices, dtype=np.int64)
        self._noise_scores = np.asarray(noise_scores, dtype=np.float32)
        self._noise_overlay_visible = bool(noise_overlay_visible)
        self._recalculate_data()
        self._render()

    def set_section(self, section: SectionData) -> None:
        self._section = section
        self._reprocess()

    def set_palette(self, palette_name: str) -> None:
        self._palette_name = str(palette_name or DEFAULT_PALETTE)
        self._render()

    def set_display_mode(self, mode: str) -> None:
        if mode not in {"wiggle", "variable_density", "wiggle_density"}:
            raise ValueError(f"Unsupported 2D display mode: {mode}")
        self._display_mode = mode
        self._render()

    def set_attribute_mode(
        self,
        attribute: str,
        parameters: AttributeParameters | None = None,
    ) -> None:
        key = str(attribute).strip().lower()
        if key not in ATTRIBUTE_NAMES:
            raise ValueError(f"Unsupported seismic attribute: {attribute}")
        self._attribute_mode = key
        if parameters is not None:
            self._attribute_parameters = parameters
        self._recalculate_data()
        self._render()

    def set_label_mode(self, mode: str) -> None:
        valid = {"auto", "trace", "cdp", "shot", "line_point", "none"}
        self._label_mode = mode if mode in valid else "auto"
        self._render_labels()

    def set_gain_settings(self, settings: GainSettings) -> None:
        self._gain_settings = settings
        self._reprocess()

    def set_qc_flags(self, flags: Iterable[QcTraceFlag]) -> None:
        self._qc_flags = list(flags)
        self._render_qc_flags()

    def set_noise_overlay(self, trace_indices: np.ndarray, scores: np.ndarray) -> None:
        self._noise_trace_indices = np.asarray(trace_indices, dtype=np.int64)
        self._noise_scores = np.asarray(scores, dtype=np.float32)
        self._render_noise_overlay()

    def set_noise_overlay_visible(self, visible: bool) -> None:
        self._noise_overlay_visible = bool(visible)
        self._render_noise_overlay()

    def set_interpretations(self, interpretations: list[InterpretationObject]) -> None:
        self._interpretations = interpretations
        self._render_interpretations()

    def begin_picking(self, kind: str, name: str, color: str = "#00E5FF") -> None:
        if kind not in {"horizon", "fault", "measurement"}:
            raise ValueError(f"Unsupported picking type: {kind}")
        self._picking_kind = kind
        self._picking_name = name.strip() or kind.title()
        self._picking_color = color
        self._measurement_start = None
        if kind != "measurement":
            active = next(
                (
                    item
                    for item in self._interpretations
                    if item.kind == kind and item.name == self._picking_name
                ),
                None,
            )
            if active is None:
                active = InterpretationObject(
                    object_id=str(uuid.uuid4()),
                    name=self._picking_name,
                    kind=kind,
                    color=color,
                )
                self._interpretations.append(active)
            self._active_object_id = active.object_id
        else:
            self._active_object_id = None
        self.plot_widget.setCursor(Qt.CrossCursor)

    def stop_picking(self) -> None:
        self._picking_kind = None
        self._active_object_id = None
        self._measurement_start = None
        self.plot_widget.unsetCursor()

    def undo_last_pick(self) -> None:
        if self._active_object_id is None:
            return
        active = self._find_active_object()
        if active is None or not active.points:
            return
        active.points.pop()
        self._render_interpretations()
        self.interpretations_changed.emit()

    def clear_active_interpretation(self) -> None:
        if self._active_object_id is None:
            return
        active = self._find_active_object()
        if active is None:
            return
        active.points.clear()
        self._render_interpretations()
        self.interpretations_changed.emit()

    def fit_view(self) -> None:
        if self._section is None or self._section.trace_count == 0:
            return
        self.plot.setXRange(-0.5, self._section.trace_count - 0.5, padding=0.005)
        start = float(self._section.time_ms[0]) if self._section.time_ms.size else 0.0
        stop = float(self._section.time_ms[-1]) if self._section.time_ms.size else 1.0
        self.plot.setYRange(start, stop, padding=0.005)

    def _recalculate_data(self) -> None:
        if self._section is None:
            self._processed = np.empty((0, 0), dtype=np.float32)
            self._display_data = np.empty((0, 0), dtype=np.float32)
            return
        self._processed = apply_gain(
            self._section.amplitudes,
            self._section.sample_interval_ms,
            self._gain_settings,
        )
        if self._attribute_mode == "amplitude":
            self._display_data = self._processed
        else:
            # Attributes are calculated from the seismic samples, not from AGC or
            # trace-balance display gain, so interpretation values remain reproducible.
            self._display_data = compute_attribute(
                self._section.amplitudes,
                self._section.sample_interval_ms,
                self._attribute_mode,
                self._attribute_parameters,
            )

    def _reprocess(self) -> None:
        self._recalculate_data()
        self._render()

    def _render(self) -> None:
        self._clear_data_items()
        if self._section is None or self._display_data.size == 0:
            self.colorbar.setVisible(False)
            self._render_labels()
            return
        self.colorbar.setVisible(self._display_mode in {"variable_density", "wiggle_density"})
        if self._display_mode in {"variable_density", "wiggle_density"}:
            self._render_density()
        if self._attribute_mode == "amplitude" and self._display_mode in {"wiggle", "wiggle_density"}:
            try:
                self._render_wiggles()
            except Exception:
                logger.exception("Wiggle rendering failed; continuing with variable-density display")
                self._wiggle_item = None
        self._render_labels()
        self._render_noise_overlay()
        self._render_qc_flags()
        self._render_interpretations()
        self.fit_view()

    def _clear_data_items(self) -> None:
        if self._image_item is not None:
            self._view_box.removeItem(self._image_item)
            self._image_item = None
        if self._wiggle_item is not None:
            self._view_box.removeItem(self._wiggle_item)
            self._wiggle_item = None
        if self._qc_item is not None:
            self._view_box.removeItem(self._qc_item)
            self._qc_item = None
        if self._noise_item is not None:
            self._view_box.removeItem(self._noise_item)
            self._noise_item = None
        for item in self._overlay_items:
            self._view_box.removeItem(item)
        self._overlay_items.clear()

    def _render_density(self) -> None:
        section = self._section
        if section is None:
            return
        image = pg.ImageItem(axisOrder="row-major")
        image.setImage(self._display_data, autoLevels=False, autoDownsample=True)
        low, high = attribute_display_range(
            self._display_data, self._attribute_mode, self._gain_settings.clip_percentile
        )
        image.setLevels((low, high))
        image.setLookupTable(palette_rgb_array(self._palette_name, 256))
        self.colorbar.set_state(low, high, self._palette_name, unit="", label=ATTRIBUTE_NAMES.get(self._attribute_mode, self._attribute_mode.title()))
        start_time = float(section.time_ms[0]) if section.time_ms.size else 0.0
        dt = (
            float(np.median(np.diff(section.time_ms)))
            if section.time_ms.size > 1
            else section.sample_interval_ms
        )
        image.setRect(QRectF(-0.5, start_time - 0.5 * dt, section.trace_count, section.sample_count * dt))
        image.setZValue(-10)
        self._view_box.addItem(image, ignoreBounds=True)
        self._image_item = image

    def _render_wiggles(self) -> None:
        section = self._section
        if section is None or section.trace_count == 0 or section.sample_count == 0:
            return
        scale = robust_scale(self._processed, 98.5)
        normalized = np.clip(self._processed / scale, -1.0, 1.0)
        maximum_curves = max(80, min(320, self.plot_widget.width() // 4))
        column_step = max(1, int(np.ceil(section.trace_count / maximum_curves)))
        columns = np.arange(0, section.trace_count, column_step, dtype=np.int64)
        traces = normalized[:, columns].T
        x_values = columns[:, None].astype(np.float32) + traces * (0.43 * column_step)
        y_values = np.broadcast_to(section.time_ms[None, :], traces.shape).astype(np.float32, copy=False)
        x_buffer = np.full((columns.size, section.sample_count + 1), np.nan, dtype=np.float32)
        y_buffer = np.full((columns.size, section.sample_count + 1), np.nan, dtype=np.float32)
        x_buffer[:, : section.sample_count] = x_values
        y_buffer[:, : section.sample_count] = y_values
        # Solid white-on-black reads as noise once density shading is behind
        # it; a translucent pen lets the wiggle trace act as an accent over
        # the density image instead of competing with it.
        color = QColor("#EAF2F8" if self._display_mode == "wiggle" else "#D9E6EE")
        color.setAlpha(255 if self._display_mode == "wiggle" else 165)
        curve = pg.PlotCurveItem(
            x=x_buffer.ravel(),
            y=y_buffer.ravel(),
            pen=pg.mkPen(color, width=0.65),
            connect="finite",
        )
        curve.setZValue(2)
        self._view_box.addItem(curve, ignoreBounds=True)
        self._wiggle_item = curve

    def _render_labels(self) -> None:
        section = self._section
        axis = self.plot.getAxis("top")
        if section is None or section.trace_count == 0 or self._label_mode == "none":
            axis.setTicks([[]])
            return
        # "line_point" (and any raw label containing a newline) renders two
        # stacked lines, which needs roughly double the horizontal clearance
        # of a single-line label or adjacent ticks start overlapping.
        is_two_line = self._label_mode == "line_point"
        label_width_px = 150 if is_two_line else 90
        available_width = max(500, self.plot_widget.width())
        maximum_labels = max(3, min(7, available_width // label_width_px))
        positions = np.linspace(0, section.trace_count - 1, maximum_labels, dtype=np.int64)
        positions = np.unique(positions)
        ticks = [(float(column), self._label_for_column(int(column))) for column in positions]
        axis.setTicks([ticks])

    def _label_for_column(self, column: int) -> str:
        section = self._section
        if section is None:
            return ""
        trace_number = int(section.trace_indices[column]) + 1
        if self._label_mode == "trace":
            return f"T{trace_number}"
        if self._label_mode == "cdp":
            value = int(section.cdp_values[column]) if section.cdp_values.size else 0
            return f"CDP {value}" if value else f"T{trace_number}"
        if self._label_mode == "shot":
            value = int(section.shot_values[column]) if section.shot_values.size else 0
            return f"SP {value}" if value else f"T{trace_number}"
        if self._label_mode == "line_point":
            line = int(section.inline_values[column]) if section.inline_values.size else 0
            point = int(section.crossline_values[column]) if section.crossline_values.size else 0
            if line or point:
                if np.any(section.cdp_values != 0):
                    return f"IL {line}\nXL {point}"
                return f"RL {line}\nRP {point}"
            return f"T{trace_number}"
        label = section.labels[column] if column < len(section.labels) else f"Trace {trace_number}"
        label = re.sub(r"\s*/\s*", "\n", label)
        label = label.replace("Trace ", "T")
        label = label.replace("Shot ", "SP ")
        return label

    def _render_noise_overlay(self) -> None:
        if self._noise_item is not None:
            self._view_box.removeItem(self._noise_item)
            self._noise_item = None
        section = self._section
        if (
            not self._noise_overlay_visible
            or section is None
            or section.trace_count == 0
            or self._noise_trace_indices.size == 0
            or self._noise_scores.size == 0
        ):
            return
        lookup = {int(trace): float(score) for trace, score in zip(self._noise_trace_indices, self._noise_scores)}
        values = np.asarray([lookup.get(int(trace), 0.0) for trace in section.trace_indices], dtype=np.float32)
        if not np.any(values > 0):
            return
        values = np.clip(values, 0.0, 1.0)
        rgba = np.zeros((1, section.trace_count, 4), dtype=np.ubyte)
        rgba[..., 0] = 255
        rgba[..., 1] = 132
        rgba[..., 2] = 32
        rgba[..., 3] = np.where(values >= 0.45, 14.0 + 46.0 * values, 0.0).astype(np.ubyte)
        start_time = float(section.time_ms[0]) if section.time_ms.size else 0.0
        stop_time = float(section.time_ms[-1]) if section.time_ms.size else start_time + 1.0
        height = max(section.sample_interval_ms, stop_time - start_time + section.sample_interval_ms)
        item = pg.ImageItem(axisOrder="row-major")
        item.setImage(rgba, autoLevels=False)
        item.setRect(QRectF(-0.5, start_time, section.trace_count, height))
        item.setZValue(4)
        self._view_box.addItem(item, ignoreBounds=True)
        self._noise_item = item

    def _render_qc_flags(self) -> None:
        if self._qc_item is not None:
            self._view_box.removeItem(self._qc_item)
            self._qc_item = None
        section = self._section
        if section is None or not self._qc_flags:
            return
        position_lookup = {int(trace): column for column, trace in enumerate(section.trace_indices)}
        start_time = float(section.time_ms[0]) if section.time_ms.size else 0.0
        stop_time = float(section.time_ms[-1]) if section.time_ms.size else 1.0
        x_values: list[float] = []
        y_values: list[float] = []
        for flag in self._qc_flags:
            column = position_lookup.get(int(flag.trace_index))
            if column is None:
                continue
            x_values.extend((float(column), float(column), np.nan))
            y_values.extend((start_time, stop_time, np.nan))
        if x_values:
            item = pg.PlotCurveItem(
                x=np.asarray(x_values),
                y=np.asarray(y_values),
                pen=pg.mkPen(QColor(255, 73, 73, 205), width=1.2),
                connect="finite",
            )
            item.setZValue(8)
            self._view_box.addItem(item, ignoreBounds=True)
            self._qc_item = item

    def _render_interpretations(self) -> None:
        for item in self._overlay_items:
            self._view_box.removeItem(item)
        self._overlay_items.clear()
        section = self._section
        if section is None:
            return
        position_lookup = {int(trace): column for column, trace in enumerate(section.trace_indices)}
        for interpretation in self._interpretations:
            if not interpretation.visible or not interpretation.points:
                continue
            visible_points = [
                (position_lookup[point.trace_index], point.time_ms)
                for point in interpretation.points
                if point.trace_index in position_lookup
            ]
            if not visible_points:
                continue
            visible_points.sort(key=lambda value: value[0])
            x = np.asarray([value[0] for value in visible_points], dtype=np.float64)
            y = np.asarray([value[1] for value in visible_points], dtype=np.float64)
            pen = pg.mkPen(
                interpretation.color,
                width=2.4 if interpretation.kind == "horizon" else 2.0,
                style=Qt.DashLine if interpretation.kind == "fault" else Qt.SolidLine,
            )
            curve = pg.PlotCurveItem(x=x, y=y, pen=pen)
            curve.setZValue(12)
            points = pg.ScatterPlotItem(
                x=x,
                y=y,
                symbol="o",
                size=5,
                brush=pg.mkBrush(interpretation.color),
                pen=pg.mkPen("#101820"),
            )
            points.setZValue(13)
            self._view_box.addItem(curve, ignoreBounds=True)
            self._view_box.addItem(points, ignoreBounds=True)
            self._overlay_items.extend((curve, points))

    def _on_mouse_moved(self, scene_position) -> None:
        section = self._section
        if section is None or self._processed.size == 0:
            return
        if not self.plot.sceneBoundingRect().contains(scene_position):
            return
        point = self.plot.getViewBox().mapSceneToView(scene_position)
        column = int(round(point.x()))
        if column < 0 or column >= section.trace_count:
            return
        sample = int(np.argmin(np.abs(section.time_ms - point.y()))) if section.time_ms.size else 0
        amplitude = float(self._processed[sample, column])
        self.cursor_changed.emit(
            int(section.trace_indices[column]),
            int(section.sample_indices[sample]),
            float(section.time_ms[sample]),
            amplitude,
        )

    def _on_mouse_clicked(self, event) -> None:
        if self._picking_kind is None or event.button() != Qt.LeftButton:
            return
        section = self._section
        if section is None or self._processed.size == 0:
            return
        position = self.plot.getViewBox().mapSceneToView(event.scenePos())
        column = int(round(position.x()))
        if column < 0 or column >= section.trace_count:
            return
        sample = int(np.argmin(np.abs(section.time_ms - position.y()))) if section.time_ms.size else 0
        sample = snap_sample(self._processed, column, sample, radius=8)
        point = InterpretationPoint(
            trace_index=int(section.trace_indices[column]),
            sample_index=int(section.sample_indices[sample]),
            time_ms=float(section.time_ms[sample]),
            x=float(section.x_coordinates[column]) if section.x_coordinates.size else None,
            y=float(section.y_coordinates[column]) if section.y_coordinates.size else None,
            inline=int(section.inline_values[column]) if section.inline_values.size else None,
            crossline=int(section.crossline_values[column]) if section.crossline_values.size else None,
            amplitude=float(self._processed[sample, column]),
        )
        if self._picking_kind == "measurement":
            self._handle_measurement(point)
            return
        active = self._find_active_object()
        if active is None:
            return
        active.points = [item for item in active.points if item.trace_index != point.trace_index]
        active.points.append(point)
        active.points.sort(key=lambda item: item.trace_index)
        self._render_interpretations()
        self.interpretations_changed.emit()

    def _handle_measurement(self, point: InterpretationPoint) -> None:
        if self._measurement_start is None:
            self._measurement_start = point
            return
        start = self._measurement_start
        delta_trace = point.trace_index - start.trace_index
        delta_time = point.time_ms - start.time_ms
        distance = None
        if None not in {start.x, start.y, point.x, point.y}:
            distance = float(np.hypot(float(point.x) - float(start.x), float(point.y) - float(start.y)))
        if distance is None:
            message = f"Measurement: Δtrace {delta_trace:+d}, Δtime {delta_time:+.2f} ms"
        else:
            message = (
                f"Measurement: Δtrace {delta_trace:+d}, Δtime {delta_time:+.2f} ms, "
                f"horizontal distance {distance:,.2f}"
            )
        self._measurement_start = None
        self.measurement_completed.emit(message)

    def _find_active_object(self) -> InterpretationObject | None:
        if self._active_object_id is None:
            return None
        return next(
            (item for item in self._interpretations if item.object_id == self._active_object_id),
            None,
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_labels()
