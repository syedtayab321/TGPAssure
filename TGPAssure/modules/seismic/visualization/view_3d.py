from __future__ import annotations

from typing import Iterable

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from matplotlib import colormaps
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from modules.seismic.visualization.models import InterpretationObject, VolumeData, WellPath
from modules.seismic.visualization.processing import robust_scale
from ui.theme.petrel_theme import FONT_SIZE_NORMAL, FONT_SIZE_SMALL


class Seismic3DView(QWidget):
    """Driver-independent interactive 3D seismic viewer.

    Earlier releases created a ``GLViewWidget`` unconditionally and therefore
    showed an OpenGL-context error on remote desktops, older Intel drivers and
    several Windows virtual/enterprise environments.  This implementation uses
    Matplotlib's Qt 3D canvas as the reliable default, so volume curtains,
    orthogonal slices, interpretations and wells remain usable without a GPU.

    The public API intentionally matches the previous OpenGL widget so the
    visualization dashboard and report exporter do not need special-case code.
    """

    gpu_status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._volume: VolumeData | None = None
        self._opacity = 0.72
        self._clip_percentile = 98.5
        self._transparency_threshold = 0.04
        self._interpretations: list[InterpretationObject] = []
        self._wells: list[WellPath] = []
        self._view_elevation = 24.0
        self._view_azimuth = -55.0
        self._last_render: tuple[str, int | None, int | None, int | None] = ("volume", None, None, None)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar_host = QFrame(self)
        toolbar_host.setStyleSheet("background:#F8FBFD;border-bottom:1px solid #D2DEE7;")
        toolbar_layout = QHBoxLayout(toolbar_host)
        toolbar_layout.setContentsMargins(5, 2, 7, 2)
        toolbar_layout.setSpacing(6)

        self.figure = Figure(figsize=(9.6, 6.0), dpi=100, facecolor="#07131F")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumSize(520, 360)
        self.navigation_toolbar = NavigationToolbar(self.canvas, toolbar_host)
        self.navigation_toolbar.setMaximumHeight(28)
        self.navigation_toolbar.setStyleSheet(
            "QToolBar{background:#F8FBFD;border:0;spacing:1px;}"
            "QToolButton{padding:1px;margin:0;min-width:22px;min-height:22px;}"
        )
        toolbar_layout.addWidget(self.navigation_toolbar, 1)

        self.backend_badge = QLabel("CPU 3D")
        self.backend_badge.setAlignment(Qt.AlignCenter)
        self.backend_badge.setFixedHeight(22)
        self.backend_badge.setMinimumWidth(70)
        self.backend_badge.setStyleSheet(
            "background:#E8F5EE;color:#166B43;border:1px solid #BBDCC9;"
            "border-radius:9px;padding:1px 8px;font-weight:700;"
        )
        self.backend_badge.setToolTip(
            "Driver-independent 3D rendering is active. No OpenGL/GPU context is required."
        )
        toolbar_layout.addWidget(self.backend_badge)
        root.addWidget(toolbar_host)
        root.addWidget(self.canvas, 1)

        self.status_label = QLabel("Load a 3D volume or seismic curtain")
        self.status_label.setObjectName("seismic3DStatusBadge")
        self.status_label.setMinimumHeight(28)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "QLabel#seismic3DStatusBadge{"
            f"background:#0C2232;color:#D8EAF5;font-size:{FONT_SIZE_SMALL}pt;"
            "border-top:1px solid #36566D;padding:5px 10px;}"
        )
        root.addWidget(self.status_label)
        self._prepare_axes("3D seismic viewer ready")

    @property
    def is_gpu_available(self) -> bool:
        # Kept for API compatibility.  Rendering no longer depends on a GPU.
        return False

    @property
    def volume(self) -> VolumeData | None:
        return self._volume

    def clear(self) -> None:
        self._volume = None
        self._interpretations = []
        self._wells = []
        self._last_render = ("volume", None, None, None)
        self._prepare_axes("Load a 3D volume or seismic curtain")
        self._set_status("3D viewer ready — driver-independent renderer active")

    def set_volume(self, volume: VolumeData, opacity: float | None = None) -> None:
        self._volume = volume
        if opacity is not None:
            self._opacity = float(np.clip(opacity, 0.08, 1.0))
        self.show_volume()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = float(np.clip(opacity, 0.08, 1.0))
        if self._volume is not None:
            self._rerender_last()

    def set_render_transfer_function(self, clip_percentile: float, transparency_threshold: float) -> None:
        self._clip_percentile = float(np.clip(clip_percentile, 50.0, 100.0))
        self._transparency_threshold = float(np.clip(transparency_threshold, 0.0, 0.95))
        if self._volume is not None:
            self._rerender_last()

    def show_volume(self) -> None:
        if self._volume is None:
            self._prepare_axes("No volume loaded")
            self._set_status("Load a 3D volume or build a seismic curtain first")
            return
        self._last_render = ("volume", None, None, None)
        volume = self._volume
        shape = volume.amplitudes.shape
        if volume.is_pseudo_volume:
            inline = shape[0] // 2
            self._render_scene(((volume.amplitudes[inline, :, :], "inline", inline),), title="SEG-D / 2D seismic curtain")
            self._set_status(f"Seismic curtain — {shape[1]:,} traces × {shape[2]:,} samples")
            return
        inline = shape[0] // 2
        crossline = shape[1] // 2
        sample = shape[2] // 2
        self._render_scene(
            (
                (volume.amplitudes[inline, :, :], "inline", inline),
                (volume.amplitudes[:, crossline, :], "crossline", crossline),
                (volume.amplitudes[:, :, sample], "time", sample),
            ),
            title="3D seismic volume — orthogonal volume probe",
        )
        self._set_status(
            f"3D volume {shape[0]} × {shape[1]} × {shape[2]} — interactive CPU rendering; drag to rotate"
        )

    def show_inline_slice(self, inline_position: int) -> None:
        if self._volume is None:
            return
        position = max(0, min(int(inline_position), self._volume.amplitudes.shape[0] - 1))
        self._last_render = ("inline", position, None, None)
        self._render_scene(((self._volume.amplitudes[position, :, :], "inline", position),), title="Inline slice")
        value = int(self._volume.inline_values[position]) if self._volume.inline_values.size > position else position
        self._set_status(f"Inline slice {value}")

    def show_crossline_slice(self, crossline_position: int) -> None:
        if self._volume is None:
            return
        position = max(0, min(int(crossline_position), self._volume.amplitudes.shape[1] - 1))
        self._last_render = ("crossline", None, position, None)
        self._render_scene(((self._volume.amplitudes[:, position, :], "crossline", position),), title="Crossline slice")
        value = int(self._volume.crossline_values[position]) if self._volume.crossline_values.size > position else position
        self._set_status(f"Crossline slice {value}")

    def show_time_slice(self, sample_position: int) -> None:
        if self._volume is None:
            return
        position = max(0, min(int(sample_position), self._volume.amplitudes.shape[2] - 1))
        self._last_render = ("time", None, None, position)
        self._render_scene(((self._volume.amplitudes[:, :, position], "time", position),), title="Time slice")
        value = float(self._volume.time_ms[position]) if self._volume.time_ms.size > position else float(position)
        self._set_status(f"Time slice {value:.1f} ms")

    def show_orthogonal_slices(
        self,
        inline_position: int | None = None,
        crossline_position: int | None = None,
        sample_position: int | None = None,
    ) -> None:
        if self._volume is None:
            return
        shape = self._volume.amplitudes.shape
        inline = shape[0] // 2 if inline_position is None else max(0, min(int(inline_position), shape[0] - 1))
        crossline = shape[1] // 2 if crossline_position is None else max(0, min(int(crossline_position), shape[1] - 1))
        sample = shape[2] // 2 if sample_position is None else max(0, min(int(sample_position), shape[2] - 1))
        self._last_render = ("orthogonal", inline, crossline, sample)
        self._render_scene(
            (
                (self._volume.amplitudes[inline, :, :], "inline", inline),
                (self._volume.amplitudes[:, crossline, :], "crossline", crossline),
                (self._volume.amplitudes[:, :, sample], "time", sample),
            ),
            title="Orthogonal inline / crossline / time probe",
        )
        inline_value = int(self._volume.inline_values[inline]) if self._volume.inline_values.size > inline else inline
        crossline_value = int(self._volume.crossline_values[crossline]) if self._volume.crossline_values.size > crossline else crossline
        time_value = float(self._volume.time_ms[sample]) if self._volume.time_ms.size > sample else float(sample)
        self._set_status(
            f"Orthogonal probe — Inline {inline_value} | Crossline {crossline_value} | {time_value:.1f} ms"
        )

    def set_interpretations(self, interpretations: Iterable[InterpretationObject]) -> None:
        self._interpretations = list(interpretations)
        if self._volume is not None:
            self._rerender_last()

    def set_wells(self, wells: Iterable[WellPath]) -> None:
        self._wells = list(wells)
        if self._volume is not None:
            self._rerender_last()

    def reset_camera(self) -> None:
        self._view_elevation = 24.0
        self._view_azimuth = -55.0
        if self.figure.axes:
            axis = self.figure.axes[0]
            try:
                axis.view_init(elev=self._view_elevation, azim=self._view_azimuth)
                self.canvas.draw_idle()
            except Exception:
                pass

    def framebuffer(self):
        # QPixmap implements save(), matching QOpenGLWidget.grabFramebuffer() for
        # the dashboard's report-image exporter.
        try:
            return self.canvas.grab()
        except Exception:
            return None

    def _rerender_last(self) -> None:
        mode, inline, crossline, sample = self._last_render
        if mode == "inline" and inline is not None:
            self.show_inline_slice(inline)
        elif mode == "crossline" and crossline is not None:
            self.show_crossline_slice(crossline)
        elif mode == "time" and sample is not None:
            self.show_time_slice(sample)
        elif mode == "orthogonal":
            self.show_orthogonal_slices(inline, crossline, sample)
        else:
            self.show_volume()

    def _prepare_axes(self, title: str):
        self.figure.clear()
        axis = self.figure.add_subplot(111, projection="3d")
        axis.set_facecolor("#07131F")
        axis.set_title(title, color="#DDEAF3", fontsize=10, pad=10)
        axis.set_xlabel("Inline / X", color="#C9D9E4", labelpad=8)
        axis.set_ylabel("Crossline / Trace", color="#C9D9E4", labelpad=8)
        axis.set_zlabel("Time / sample", color="#C9D9E4", labelpad=8)
        axis.tick_params(colors="#AFC4D2", labelsize=7)
        try:
            axis.xaxis.pane.set_facecolor((0.04, 0.10, 0.15, 1.0))
            axis.yaxis.pane.set_facecolor((0.04, 0.10, 0.15, 1.0))
            axis.zaxis.pane.set_facecolor((0.04, 0.10, 0.15, 1.0))
            axis.xaxis.pane.set_edgecolor("#38566A")
            axis.yaxis.pane.set_edgecolor("#38566A")
            axis.zaxis.pane.set_edgecolor("#38566A")
        except Exception:
            pass
        axis.grid(True, alpha=0.18)
        axis.view_init(elev=self._view_elevation, azim=self._view_azimuth)
        try:
            axis.set_box_aspect((1.15, 1.0, 0.82))
        except Exception:
            pass
        self.canvas.draw_idle()
        return axis

    def _render_scene(self, specifications, *, title: str) -> None:
        if self._volume is None:
            return
        axis = self._prepare_axes(title)
        for data, plane, position in specifications:
            self._plot_slice(axis, np.asarray(data, dtype=float), plane, int(position))
        self._plot_interpretations(axis)
        self._plot_wells(axis)
        axis.set_xlim(-50.0, 50.0)
        axis.set_ylim(-50.0, 50.0)
        axis.set_zlim(-45.0, 45.0)
        self.figure.subplots_adjust(left=0.0, right=0.98, bottom=0.02, top=0.93)
        self.canvas.draw_idle()

    def _plot_slice(self, axis, data: np.ndarray, plane: str, position: int) -> None:
        if self._volume is None or data.ndim != 2:
            return
        first_step = max(1, int(np.ceil(data.shape[0] / 115)))
        second_step = max(1, int(np.ceil(data.shape[1] / 180)))
        reduced = data[::first_step, ::second_step]
        if reduced.shape[0] < 2 or reduced.shape[1] < 2:
            reduced = np.pad(reduced, ((0, max(0, 2 - reduced.shape[0])), (0, max(0, 2 - reduced.shape[1]))))

        scale = robust_scale(reduced, self._clip_percentile)
        if not np.isfinite(scale) or scale <= 0:
            scale = 1.0
        normalized = np.clip(np.nan_to_num(reduced / scale, nan=0.0), -1.0, 1.0)
        colors = colormaps["seismic"]((normalized + 1.0) * 0.5)
        magnitude = np.abs(normalized)
        alpha = np.where(
            magnitude >= self._transparency_threshold,
            self._opacity,
            max(0.08, self._opacity * 0.24),
        )
        colors[..., 3] = alpha

        rows, columns = reduced.shape
        rr, cc = np.mgrid[0:rows, 0:columns]
        shape = self._volume.amplitudes.shape
        x_scale = 100.0 / max(1, shape[0] - 1)
        y_scale = 100.0 / max(1, shape[1] - 1)
        z_scale = 90.0 / max(1, shape[2] - 1)

        if plane == "inline":
            x_position = 0.0 if self._volume.is_pseudo_volume else position * x_scale - 50.0
            x = np.full_like(rr, x_position, dtype=float)
            y = rr.astype(float) * first_step * y_scale - 50.0
            z = 45.0 - cc.astype(float) * second_step * z_scale
        elif plane == "crossline":
            x = rr.astype(float) * first_step * x_scale - 50.0
            y = np.full_like(rr, position * y_scale - 50.0, dtype=float)
            z = 45.0 - cc.astype(float) * second_step * z_scale
        else:
            x = rr.astype(float) * first_step * x_scale - 50.0
            y = cc.astype(float) * second_step * y_scale - 50.0
            z = np.full_like(rr, 45.0 - position * z_scale, dtype=float)

        axis.plot_surface(
            x,
            y,
            z,
            facecolors=colors,
            rstride=1,
            cstride=1,
            linewidth=0,
            antialiased=False,
            shade=False,
        )

    def _plot_interpretations(self, axis) -> None:
        if self._volume is None:
            return
        for interpretation in self._interpretations:
            if not interpretation.visible or len(interpretation.points) < 2:
                continue
            positions = np.asarray([self._point_to_scene(point) for point in interpretation.points], dtype=float)
            axis.plot(
                positions[:, 0],
                positions[:, 1],
                positions[:, 2],
                color=interpretation.color,
                linewidth=2.0 if interpretation.kind == "horizon" else 1.7,
                label=interpretation.name,
            )

    def _plot_wells(self, axis) -> None:
        for well in self._wells:
            if min(well.x.size, well.y.size, well.z.size) < 2:
                continue
            positions = self._well_to_scene(np.column_stack((well.x, well.y, well.z)).astype(float))
            axis.plot(positions[:, 0], positions[:, 1], positions[:, 2], color=well.color, linewidth=2.4)

    def _point_to_scene(self, point) -> tuple[float, float, float]:
        volume = self._volume
        if volume is None:
            return 0.0, 0.0, 0.0
        if point.inline is not None and volume.inline_values.size:
            inline_position = int(np.argmin(np.abs(volume.inline_values - point.inline)))
        else:
            inline_position = volume.amplitudes.shape[0] // 2 if volume.is_pseudo_volume else 0
        if point.crossline is not None and volume.crossline_values.size:
            crossline_position = int(np.argmin(np.abs(volume.crossline_values - point.crossline)))
        else:
            crossline_position = max(0, min(point.trace_index, volume.amplitudes.shape[1] - 1))
        sample_position = int(np.argmin(np.abs(volume.time_ms - point.time_ms))) if volume.time_ms.size else 0
        x = 0.0 if volume.is_pseudo_volume else inline_position / max(1, volume.amplitudes.shape[0] - 1) * 100.0 - 50.0
        y = crossline_position / max(1, volume.amplitudes.shape[1] - 1) * 100.0 - 50.0
        z = 45.0 - sample_position / max(1, volume.amplitudes.shape[2] - 1) * 90.0
        return float(x), float(y), float(z)

    def _well_to_scene(self, positions: np.ndarray) -> np.ndarray:
        result = positions.copy()
        volume = self._volume
        for axis_index, coordinate_grid in (
            (0, None if volume is None else volume.x_coordinates),
            (1, None if volume is None else volume.y_coordinates),
        ):
            values = result[:, axis_index]
            finite_grid = (
                np.asarray(coordinate_grid, dtype=float)[np.isfinite(coordinate_grid)]
                if coordinate_grid is not None
                else np.empty(0, dtype=float)
            )
            if finite_grid.size >= 2 and float(np.max(finite_grid)) > float(np.min(finite_grid)):
                minimum = float(np.min(finite_grid))
                maximum = float(np.max(finite_grid))
            else:
                minimum = float(np.min(values))
                maximum = float(np.max(values))
            result[:, axis_index] = (
                (values - minimum) / (maximum - minimum) * 100.0 - 50.0
                if maximum > minimum
                else 0.0
            )
        vertical = result[:, 2]
        minimum_z = float(np.min(vertical))
        maximum_z = float(np.max(vertical))
        result[:, 2] = (
            45.0 - (vertical - minimum_z) / (maximum_z - minimum_z) * 90.0
            if maximum_z > minimum_z
            else 0.0
        )
        return result

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.gpu_status_changed.emit(message)
