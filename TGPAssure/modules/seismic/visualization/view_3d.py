from __future__ import annotations

from typing import Iterable

import numpy as np
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QShowEvent, QVector3D
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QWidget
from scipy.spatial import Delaunay

from modules.seismic.visualization.models import InterpretationObject, VolumeData, WellPath
from modules.seismic.visualization.processing import normalized_rgba_volume, robust_scale
from ui.theme.petrel_theme import FONT_SIZE_NORMAL, FONT_SIZE_SMALL

try:
    import pyqtgraph.opengl as gl

    OPENGL_AVAILABLE = True
except Exception:
    gl = None
    OPENGL_AVAILABLE = False


class Seismic3DView(QWidget):
    gpu_status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._volume: VolumeData | None = None
        self._opacity = 0.48
        self._clip_percentile = 98.5
        self._transparency_threshold = 0.04
        self._interpretations: list[InterpretationObject] = []
        self._wells: list[WellPath] = []
        self._volume_item = None
        self._slice_item = None
        self._slice_items: list[object] = []
        self._surface_items: list[object] = []
        self._well_items: list[object] = []
        self._grid_items: list[object] = []
        self._gpu_ready = False
        self._gpu_checked = False

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not OPENGL_AVAILABLE:
            self.view = None
            placeholder = QFrame()
            placeholder.setStyleSheet("background:#07131F;border:1px solid #24384A;")
            placeholder_layout = QGridLayout(placeholder)
            message = QLabel(
                "GPU 3D rendering is unavailable. Install PyOpenGL and use an OpenGL-capable display driver."
            )
            message.setAlignment(Qt.AlignCenter)
            message.setWordWrap(True)
            message.setStyleSheet(f"color:#D8E6F2;font-size:{FONT_SIZE_NORMAL}pt;padding:30px;")
            placeholder_layout.addWidget(message)
            layout.addWidget(placeholder, 0, 0)
            self.status_label = QLabel("OpenGL unavailable")
            self.status_label.setVisible(False)
            return

        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor(QColor("#07131F"))
        self.view.setMinimumSize(500, 380)
        self.view.setCameraPosition(
            pos=QVector3D(0.0, 0.0, 0.0),
            distance=175,
            elevation=24,
            azimuth=35,
        )
        layout.addWidget(self.view, 0, 0)

        self.status_label = QLabel("Initializing GPU/OpenGL rendering")
        self.status_label.setObjectName("seismic3DStatusBadge")
        self.status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.status_label.setMinimumHeight(28)
        self.status_label.setMaximumHeight(28)
        self.status_label.setMaximumWidth(720)
        self.status_label.setStyleSheet(
            "QLabel#seismic3DStatusBadge{"
            f"background:rgba(12,34,50,220);color:#D8EAF5;font-size:{FONT_SIZE_SMALL}pt;"
            "border:1px solid #36566D;border-radius:4px;padding:4px 10px;}"
        )
        layout.addWidget(self.status_label, 0, 0, Qt.AlignLeft | Qt.AlignBottom)

    @property
    def is_gpu_available(self) -> bool:
        return bool(OPENGL_AVAILABLE and self.view is not None and self._gpu_ready)

    @property
    def volume(self) -> VolumeData | None:
        return self._volume

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if OPENGL_AVAILABLE and self.view is not None and not self._gpu_checked:
            QTimer.singleShot(0, self._initialize_gpu)

    def _initialize_gpu(self) -> None:
        if self.view is None or self._gpu_checked:
            return
        self._gpu_checked = True
        self._gpu_ready = bool(self.view.isValid())
        if self._gpu_ready:
            self._create_scene_reference()
            self._set_status("GPU/OpenGL rendering enabled")
            if self._volume is not None:
                self.show_volume()
        else:
            self._set_status(
                "OpenGL context is unavailable. Update the graphics driver to enable 3D rendering."
            )

    def clear(self) -> None:
        self._volume = None
        self._interpretations = []
        self._wells = []
        if self.is_gpu_available:
            self._remove_primary_items()
            self._remove_items(self._surface_items)
            self._remove_items(self._well_items)
        if not OPENGL_AVAILABLE:
            message = "GPU 3D rendering is unavailable"
        elif self._gpu_checked and not self._gpu_ready:
            message = "OpenGL context is unavailable"
        else:
            message = "Load a 3D volume or seismic curtain"
        self._set_status(message)

    def set_volume(self, volume: VolumeData, opacity: float | None = None) -> None:
        self._volume = volume
        if opacity is not None:
            self._opacity = float(np.clip(opacity, 0.05, 1.0))
        shape_text = " × ".join(str(value) for value in volume.shape)
        mode = "seismic curtain" if volume.is_pseudo_volume else "3D volume"
        if self.is_gpu_available:
            self.show_volume()
            self._set_status(f"{mode.title()} {shape_text}")
        elif not self._gpu_checked:
            self._set_status(f"{mode.title()} {shape_text} loaded; initializing OpenGL")
        else:
            self._set_status(f"{mode.title()} {shape_text} loaded; OpenGL unavailable")

    def set_opacity(self, opacity: float) -> None:
        self._opacity = float(np.clip(opacity, 0.05, 1.0))
        if self._volume is not None and self.is_gpu_available:
            self.show_volume()

    def set_render_transfer_function(
        self,
        clip_percentile: float,
        transparency_threshold: float,
    ) -> None:
        self._clip_percentile = float(np.clip(clip_percentile, 50.0, 100.0))
        self._transparency_threshold = float(np.clip(transparency_threshold, 0.0, 0.95))
        if self._volume is not None and self.is_gpu_available:
            self.show_volume()

    def show_volume(self) -> None:
        if not self.is_gpu_available or self._volume is None:
            return
        if self._volume.is_pseudo_volume:
            middle = self._volume.amplitudes.shape[0] // 2
            data = self._volume.amplitudes[middle, :, :]
            self._show_slice_mesh(data, plane="inline", position=middle, curtain=True)
            self._set_status("SEG-D/2D seismic curtain view")
            return
        self._remove_primary_items()
        rgba = normalized_rgba_volume(
            self._volume.amplitudes,
            self._opacity,
            clip_percentile=self._clip_percentile,
            transparency_threshold=self._transparency_threshold,
        )
        item = gl.GLVolumeItem(
            rgba,
            sliceDensity=1,
            smooth=False,
            glOptions="translucent",
        )
        self._scale_and_center(item, rgba.shape[:3])
        self.view.addItem(item)
        self._volume_item = item
        self._render_surfaces()
        self._render_wells()
        self._set_status("3D volume rendering")

    def show_inline_slice(self, inline_position: int) -> None:
        if self._volume is None:
            return
        position = max(0, min(int(inline_position), self._volume.amplitudes.shape[0] - 1))
        data = self._volume.amplitudes[position, :, :]
        self._show_slice_mesh(data, plane="inline", position=position)
        value = (
            int(self._volume.inline_values[position])
            if self._volume.inline_values.size > position
            else position
        )
        self._set_status(f"Inline slice {value}")

    def show_crossline_slice(self, crossline_position: int) -> None:
        if self._volume is None:
            return
        position = max(0, min(int(crossline_position), self._volume.amplitudes.shape[1] - 1))
        data = self._volume.amplitudes[:, position, :]
        self._show_slice_mesh(data, plane="crossline", position=position)
        value = (
            int(self._volume.crossline_values[position])
            if self._volume.crossline_values.size > position
            else position
        )
        self._set_status(f"Crossline slice {value}")

    def show_time_slice(self, sample_position: int) -> None:
        if self._volume is None:
            return
        position = max(0, min(int(sample_position), self._volume.amplitudes.shape[2] - 1))
        data = self._volume.amplitudes[:, :, position]
        self._show_slice_mesh(data, plane="time", position=position)
        value = (
            float(self._volume.time_ms[position])
            if self._volume.time_ms.size > position
            else float(position)
        )
        self._set_status(f"Time slice {value:.1f} ms")

    def show_orthogonal_slices(
        self,
        inline_position: int | None = None,
        crossline_position: int | None = None,
        sample_position: int | None = None,
    ) -> None:
        """Display synchronized inline, crossline and time probes in one 3D scene."""
        if not self.is_gpu_available or self._volume is None:
            return
        shape = self._volume.amplitudes.shape
        inline = shape[0] // 2 if inline_position is None else max(0, min(int(inline_position), shape[0] - 1))
        crossline = shape[1] // 2 if crossline_position is None else max(0, min(int(crossline_position), shape[1] - 1))
        sample = shape[2] // 2 if sample_position is None else max(0, min(int(sample_position), shape[2] - 1))
        self._remove_primary_items()
        specifications = (
            (self._volume.amplitudes[inline, :, :], "inline", inline),
            (self._volume.amplitudes[:, crossline, :], "crossline", crossline),
            (self._volume.amplitudes[:, :, sample], "time", sample),
        )
        for data, plane, position in specifications:
            mesh = self._build_slice_mesh(np.asarray(data, dtype=np.float32), plane, position, False)
            self.view.addItem(mesh)
            self._slice_items.append(mesh)
        self._render_surfaces()
        self._render_wells()
        inline_value = int(self._volume.inline_values[inline]) if self._volume.inline_values.size > inline else inline
        crossline_value = int(self._volume.crossline_values[crossline]) if self._volume.crossline_values.size > crossline else crossline
        time_value = float(self._volume.time_ms[sample]) if self._volume.time_ms.size > sample else float(sample)
        self._set_status(
            f"Orthogonal probe — Inline {inline_value} | Crossline {crossline_value} | {time_value:.1f} ms"
        )

    def set_interpretations(self, interpretations: Iterable[InterpretationObject]) -> None:
        self._interpretations = list(interpretations)
        self._render_surfaces()

    def set_wells(self, wells: Iterable[WellPath]) -> None:
        self._wells = list(wells)
        self._render_wells()

    def reset_camera(self) -> None:
        if self.is_gpu_available:
            self.view.setCameraPosition(
                pos=QVector3D(0.0, 0.0, 0.0),
                distance=175,
                elevation=24,
                azimuth=35,
            )

    def framebuffer(self):
        if not self.is_gpu_available:
            return None
        return self.view.grabFramebuffer()

    def _set_status(self, message: str) -> None:
        if hasattr(self, "status_label"):
            self.status_label.setText(message)
        self.gpu_status_changed.emit(message)

    def _create_scene_reference(self) -> None:
        if not self.is_gpu_available or self._grid_items:
            return
        floor = gl.GLGridItem()
        floor.setSize(100, 100, 1)
        floor.setSpacing(10, 10, 1)
        floor.translate(0, 0, -45)
        self.view.addItem(floor)
        self._grid_items.append(floor)

        back = gl.GLGridItem()
        back.setSize(100, 90, 1)
        back.setSpacing(10, 10, 1)
        back.rotate(90, 1, 0, 0)
        back.translate(0, 50, 0)
        self.view.addItem(back)
        self._grid_items.append(back)

        side = gl.GLGridItem()
        side.setSize(100, 90, 1)
        side.setSpacing(10, 10, 1)
        side.rotate(90, 0, 1, 0)
        side.translate(-50, 0, 0)
        self.view.addItem(side)
        self._grid_items.append(side)

        axis = gl.GLAxisItem()
        axis.setSize(32, 32, 32)
        axis.translate(-50, -50, -45)
        self.view.addItem(axis)
        self._grid_items.append(axis)

        edges = [
            ((-50, -50, -45), (50, -50, -45)),
            ((-50, 50, -45), (50, 50, -45)),
            ((-50, -50, 45), (50, -50, 45)),
            ((-50, 50, 45), (50, 50, 45)),
            ((-50, -50, -45), (-50, 50, -45)),
            ((50, -50, -45), (50, 50, -45)),
            ((-50, -50, 45), (-50, 50, 45)),
            ((50, -50, 45), (50, 50, 45)),
            ((-50, -50, -45), (-50, -50, 45)),
            ((50, -50, -45), (50, -50, 45)),
            ((-50, 50, -45), (-50, 50, 45)),
            ((50, 50, -45), (50, 50, 45)),
        ]
        positions = np.asarray([point for edge in edges for point in edge], dtype=np.float32)
        box = gl.GLLinePlotItem(
            pos=positions,
            color=(0.45, 0.65, 0.78, 0.55),
            width=1.0,
            antialias=True,
            mode="lines",
        )
        self.view.addItem(box)
        self._grid_items.append(box)

    def _remove_primary_items(self) -> None:
        if not self.is_gpu_available:
            return
        primary_items = [self._volume_item, self._slice_item, *self._slice_items]
        seen: set[int] = set()
        for item in primary_items:
            if item is not None and id(item) not in seen:
                seen.add(id(item))
                try:
                    self.view.removeItem(item)
                except Exception:
                    pass
        self._volume_item = None
        self._slice_item = None
        self._slice_items.clear()

    def _remove_items(self, items: list[object]) -> None:
        if not self.is_gpu_available:
            items.clear()
            return
        for item in items:
            try:
                self.view.removeItem(item)
            except Exception:
                pass
        items.clear()

    def _show_slice_mesh(
        self,
        data: np.ndarray,
        plane: str,
        position: int,
        curtain: bool = False,
    ) -> None:
        if not self.is_gpu_available or self._volume is None:
            return
        self._remove_primary_items()
        mesh = self._build_slice_mesh(
            np.asarray(data, dtype=np.float32),
            plane,
            position,
            curtain,
        )
        self.view.addItem(mesh)
        self._slice_item = mesh
        self._slice_items = [mesh]
        self._render_surfaces()
        self._render_wells()

    def _build_slice_mesh(
        self,
        data: np.ndarray,
        plane: str,
        position: int,
        curtain: bool,
    ):
        first_step = max(1, int(np.ceil(data.shape[0] / 150)))
        second_step = max(1, int(np.ceil(data.shape[1] / 220)))
        reduced = data[::first_step, ::second_step]
        rows, columns = reduced.shape
        if rows < 2 or columns < 2:
            reduced = np.pad(
                reduced,
                ((0, max(0, 2 - rows)), (0, max(0, 2 - columns))),
            )
            rows, columns = reduced.shape

        valid_samples = np.isfinite(reduced)
        scale = robust_scale(reduced, 98.5)
        normalized = np.where(valid_samples, np.clip(reduced / scale, -1.0, 1.0), 0.0)
        grid_r, grid_c = np.mgrid[0:rows, 0:columns]
        x_scale = 100.0 / max(1, self._volume.amplitudes.shape[0] - 1)
        y_scale = 100.0 / max(1, self._volume.amplitudes.shape[1] - 1)
        z_scale = 90.0 / max(1, self._volume.amplitudes.shape[2] - 1)

        if plane == "inline":
            x_position = 0.0 if curtain else position * x_scale - 50.0
            x = np.full_like(grid_r, x_position, dtype=np.float32)
            y = grid_r.astype(np.float32) * first_step * y_scale - 50.0
            z = 45.0 - grid_c.astype(np.float32) * second_step * z_scale
        elif plane == "crossline":
            x = grid_r.astype(np.float32) * first_step * x_scale - 50.0
            y = np.full_like(grid_r, position * y_scale - 50.0, dtype=np.float32)
            z = 45.0 - grid_c.astype(np.float32) * second_step * z_scale
        else:
            x = grid_r.astype(np.float32) * first_step * x_scale - 50.0
            y = grid_c.astype(np.float32) * second_step * y_scale - 50.0
            relief = normalized * 1.8
            z = np.full_like(grid_r, 45.0 - position * z_scale, dtype=np.float32) + relief

        vertices = np.column_stack((x.ravel(), y.ravel(), z.ravel())).astype(np.float32)
        cell_rows = np.arange(rows - 1)[:, None]
        cell_columns = np.arange(columns - 1)[None, :]
        a = cell_rows * columns + cell_columns
        b = a + 1
        c = a + columns
        d = c + 1
        faces = np.stack(
            (
                np.stack((a, b, c), axis=-1),
                np.stack((b, d, c), axis=-1),
            ),
            axis=2,
        ).reshape(-1, 3).astype(np.uint32)

        cell_values = 0.25 * (
            normalized[:-1, :-1]
            + normalized[1:, :-1]
            + normalized[:-1, 1:]
            + normalized[1:, 1:]
        )
        cell_valid = (
            valid_samples[:-1, :-1]
            & valid_samples[1:, :-1]
            & valid_samples[:-1, 1:]
            & valid_samples[1:, 1:]
        )
        face_valid = np.repeat(cell_valid.ravel(), 2)
        faces = faces[face_valid]
        values = np.repeat(cell_values.ravel(), 2)[face_valid]
        magnitude = np.clip(np.abs(values), 0.0, 1.0)
        colors = np.empty((values.size, 4), dtype=np.float32)
        positive = values >= 0
        colors[:, 0] = np.where(positive, 1.0, 1.0 - magnitude)
        colors[:, 1] = 1.0 - magnitude
        colors[:, 2] = np.where(positive, 1.0 - magnitude, 1.0)
        colors[:, 3] = 0.98

        mesh_data = gl.MeshData(
            vertexes=vertices,
            faces=faces,
            faceColors=colors,
        )
        return gl.GLMeshItem(
            meshdata=mesh_data,
            smooth=False,
            drawEdges=False,
            glOptions="opaque",
        )

    def _render_surfaces(self) -> None:
        if not self.is_gpu_available:
            return
        self._remove_items(self._surface_items)
        if self._volume is None:
            return
        for interpretation in self._interpretations:
            if (
                not interpretation.visible
                or interpretation.kind not in {"horizon", "fault"}
                or len(interpretation.points) < 2
            ):
                continue
            positions = np.asarray(
                [self._point_to_scene(point) for point in interpretation.points],
                dtype=np.float32,
            )
            line = gl.GLLinePlotItem(
                pos=positions,
                color=self._color_tuple(interpretation.color, 1.0),
                width=2.5,
                antialias=True,
                mode="line_strip",
            )
            self.view.addItem(line)
            self._surface_items.append(line)
            if interpretation.kind == "horizon" and positions.shape[0] >= 3:
                try:
                    triangulation = Delaunay(positions[:, :2])
                    colors = np.tile(
                        np.asarray(
                            self._color_tuple(interpretation.color, 0.34),
                            dtype=np.float32,
                        ),
                        (triangulation.simplices.shape[0], 1),
                    )
                    mesh_data = gl.MeshData(
                        vertexes=positions,
                        faces=triangulation.simplices,
                        faceColors=colors,
                    )
                    surface = gl.GLMeshItem(
                        meshdata=mesh_data,
                        smooth=False,
                        drawEdges=False,
                        glOptions="translucent",
                    )
                    self.view.addItem(surface)
                    self._surface_items.append(surface)
                except Exception:
                    pass

    def _render_wells(self) -> None:
        if not self.is_gpu_available:
            return
        self._remove_items(self._well_items)
        for well in self._wells:
            if min(well.x.size, well.y.size, well.z.size) < 2:
                continue
            positions = np.column_stack((well.x, well.y, well.z)).astype(np.float32)
            positions = self._well_to_scene(positions)
            line = gl.GLLinePlotItem(
                pos=positions,
                color=self._color_tuple(well.color, 1.0),
                width=3.0,
                antialias=True,
                mode="line_strip",
            )
            self.view.addItem(line)
            self._well_items.append(line)

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
        sample_position = (
            int(np.argmin(np.abs(volume.time_ms - point.time_ms)))
            if volume.time_ms.size
            else 0
        )
        x = 0.0 if volume.is_pseudo_volume else inline_position / max(1, volume.amplitudes.shape[0] - 1) * 100.0 - 50.0
        y = crossline_position / max(1, volume.amplitudes.shape[1] - 1) * 100.0 - 50.0
        z = 45.0 - sample_position / max(1, volume.amplitudes.shape[2] - 1) * 90.0
        return float(x), float(y), float(z)

    def _well_to_scene(self, positions: np.ndarray) -> np.ndarray:
        result = positions.copy()
        volume = self._volume
        for axis, coordinate_grid in (
            (0, None if volume is None else volume.x_coordinates),
            (1, None if volume is None else volume.y_coordinates),
        ):
            values = result[:, axis]
            finite_grid = (
                np.asarray(coordinate_grid, dtype=np.float64)[np.isfinite(coordinate_grid)]
                if coordinate_grid is not None
                else np.empty(0, dtype=np.float64)
            )
            if finite_grid.size >= 2 and float(np.max(finite_grid)) > float(np.min(finite_grid)):
                minimum = float(np.min(finite_grid))
                maximum = float(np.max(finite_grid))
            else:
                minimum = float(np.min(values))
                maximum = float(np.max(values))
            if maximum > minimum:
                result[:, axis] = (values - minimum) / (maximum - minimum) * 100.0 - 50.0
            else:
                result[:, axis] = 0.0
        vertical = result[:, 2]
        minimum_z = float(np.min(vertical))
        maximum_z = float(np.max(vertical))
        if maximum_z > minimum_z:
            result[:, 2] = 45.0 - (vertical - minimum_z) / (maximum_z - minimum_z) * 90.0
        else:
            result[:, 2] = 0.0
        return result

    @staticmethod
    def _scale_and_center(item, shape: tuple[int, int, int]) -> None:
        sx = 100.0 / max(1, shape[0])
        sy = 100.0 / max(1, shape[1])
        sz = 90.0 / max(1, shape[2])
        item.scale(sx, sy, sz)
        item.translate(-50.0, -50.0, -45.0)

    @staticmethod
    def _color_tuple(value: str, alpha: float) -> tuple[float, float, float, float]:
        color = QColor(value)
        return color.redF(), color.greenF(), color.blueF(), float(alpha)