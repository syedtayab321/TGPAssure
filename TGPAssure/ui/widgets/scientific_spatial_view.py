from __future__ import annotations

from dataclasses import dataclass
import logging
import os

import numpy as np
import pyqtgraph as pg

try:
    import matplotlib as mpl
    from matplotlib import cm
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.colors import ListedColormap, Normalize
    from matplotlib.figure import Figure
    from matplotlib.tri import Triangulation
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 - activates matplotlib 3D projection
except Exception:  # Matplotlib is optional; pyqtgraph fallback remains available.
    mpl = None
    FigureCanvas = None
    NavigationToolbar = None
    Figure = None
    Triangulation = None
    Normalize = None
    ListedColormap = None
    cm = None

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.domain.spatial_visualization import (
    deterministic_decimation_indices,
    finite_xyzv,
    grid_scattered_surface,
    normalize_robust,
    value_relief,
)
from core.visualization.palette_library import (
    DEFAULT_PALETTE,
    palette_rgba_array,
    palette_rgb_array,
)
from ui.widgets.color_palette_dialog import PaletteSelectorButton
from ui.widgets.palette_colorbar import PaletteColorBar

# PyOpenGL logs the absence of its optional Cython accelerator at INFO level.
logging.getLogger("OpenGL.acceleratesupport").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

try:
    import pyqtgraph.opengl as gl
except Exception:  # OpenGL can be unavailable on headless/remote/old-driver systems.
    gl = None

_USE_NATIVE_OPENGL_3D = os.environ.get("TGPASSURE_OPENGL_3D", "0").strip().lower() in {"1", "true", "yes", "on"}

_SPATIAL_QSS = """
QWidget { background: #F4F7FA; color: #102A3D; font-size: 8pt; }
QFrame#scientificSpatialToolbar {
    background: #FFFFFF; border: 1px solid #D4DEE8; border-radius: 7px;
}
QLabel#spatialTitle { color:#123047; font-size:9px; font-weight:900; }
QLabel#spatialStatus { color:#5D7080; font-size:7.7px; padding:2px 4px; }
QComboBox {
    min-height: 21px; max-height: 23px; border: 1px solid #BCCBD6; border-radius: 5px;
    background: #FFFFFF; padding: 1px 7px; font-size:8px;
}
QPushButton {
    min-height: 20px; max-height: 22px; border: 1px solid #B7C7D2; border-radius: 5px;
    background: #FFFFFF; padding: 1px 6px; font-size:7.6px; font-weight:800;
}
QPushButton:hover { background:#EAF3F8; border-color:#1787B9; }
QPushButton#spatialPrimaryButton { background:#0D83BB; color:#FFFFFF; border-color:#0870A2; }
QPushButton#spatialPrimaryButton:hover { background:#0B73A5; }
"""


@dataclass
class _SpatialPayload:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    values: np.ndarray
    title: str
    value_label: str
    value_units: str
    coordinate_label: str
    allow_surface: bool


class ScientificSpatialView(QWidget):
    """Reusable professional 2D/3D scientific viewer for geophysical QC datasets.

    The widget is shared by Electrical, Magnetic and Geodetic modules. It now uses
    a true Matplotlib 3D canvas when available, with adaptive rendering for:

    * profile / pseudosection datasets such as ERT, IP, VES and uphole-style lines;
    * full XY/Z spatial datasets such as magnetic, gravity/geodetic and 3D arrays;
    * safe pyqtgraph fallback where Matplotlib/OpenGL is unavailable.

    Native OpenGL remains optional through TGPASSURE_OPENGL_3D=1, but Matplotlib is
    the default because it avoids driver black screens and gives reliable export.
    """

    def __init__(self, parent: QWidget | None = None, *, title: str = "2D / 3D Data View") -> None:
        super().__init__(parent)
        self.setStyleSheet(_SPATIAL_QSS)
        self._payload: _SpatialPayload | None = None
        self._last_mode = "2d"
        self._view_preset = "oblique"
        self._zoom_factor = 1.0
        self._mpl_scroll_connection = None
        self._palette_name = DEFAULT_PALETTE
        self._build_ui(title)

    def _build_ui(self, title: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        toolbar = QFrame(self)
        toolbar.setObjectName("scientificSpatialToolbar")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(5)
        toolbar.setMaximumHeight(29)

        heading = QLabel(title)
        heading.setObjectName("spatialTitle")
        row.addWidget(heading)
        row.addStretch(1)

        label = QLabel("View:")
        label.setStyleSheet("font-size:8px;color:#516A7B;background:transparent;")
        row.addWidget(label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("2D Map / Section", "2d")
        self.mode_combo.addItem("3D Spatial", "3d_spatial")
        self.mode_combo.addItem("3D Value Relief", "3d_relief")
        self.mode_combo.setFixedWidth(154)
        self.mode_combo.currentIndexChanged.connect(self._render)
        row.addWidget(self.mode_combo)

        palette_label = QLabel("Palette:")
        palette_label.setStyleSheet("font-size:8px;color:#516A7B;background:transparent;")
        row.addWidget(palette_label)
        self.palette_selector = PaletteSelectorButton(self._palette_name, toolbar)
        self.palette_selector.setMinimumWidth(128)
        self.palette_selector.currentTextChanged.connect(self.set_palette)
        row.addWidget(self.palette_selector)

        self.fit_button = QPushButton("Fit")
        self.fit_button.setObjectName("spatialPrimaryButton")
        self.fit_button.setToolTip("Refit the current 2D/3D view to the dataset extents")
        self.fit_button.clicked.connect(self._fit_view)
        row.addWidget(self.fit_button)
        for label_text, preset in (("Top", "top"), ("Side", "side"), ("Oblique", "oblique")):
            btn = QPushButton(label_text)
            btn.setToolTip(f"Set {label_text.lower()} scientific 3D view")
            btn.clicked.connect(lambda _=False, p=preset: self._set_view_preset(p))
            row.addWidget(btn)
        zoom_in = QPushButton("+")
        zoom_in.setToolTip("Zoom in on the current 3D data extents")
        zoom_in.clicked.connect(lambda: self._zoom_3d(0.72))
        row.addWidget(zoom_in)
        zoom_out = QPushButton("−")
        zoom_out.setToolTip("Zoom out from the current 3D data extents")
        zoom_out.clicked.connect(lambda: self._zoom_3d(1.34))
        row.addWidget(zoom_out)
        root.addWidget(toolbar)

        self.stack = QStackedWidget(self)
        self.plot_2d = pg.PlotWidget(background="w")
        self._prepare_plot(self.plot_2d)
        self.stack.addWidget(self.plot_2d)

        self.plot_3d_fallback = pg.PlotWidget(background="w")
        self._prepare_plot(self.plot_3d_fallback)

        self.view_3d = None
        self.figure_3d = None
        self.canvas_3d = None
        self.toolbar_3d = None
        self._three_d_backend = "projected"
        self._three_d_stack_index = -1
        self._fallback_stack_index = -1

        if FigureCanvas is not None and Figure is not None:
            self._three_d_backend = "matplotlib"
            mpl_holder = QWidget(self)
            mpl_holder.setStyleSheet("background:#FFFFFF;")
            mpl_layout = QVBoxLayout(mpl_holder)
            mpl_layout.setContentsMargins(0, 0, 0, 0)
            mpl_layout.setSpacing(0)
            self.figure_3d = Figure(figsize=(9.4, 5.5), dpi=100, facecolor="white")
            self.canvas_3d = FigureCanvas(self.figure_3d)
            try:
                self.canvas_3d.setStyleSheet("background:#FFFFFF;")
                self.canvas_3d.setFocusPolicy(Qt.StrongFocus)
                self.canvas_3d.setFocus()
                self._mpl_scroll_connection = self.canvas_3d.mpl_connect("scroll_event", self._on_mpl_scroll)
            except Exception:
                pass
            if NavigationToolbar is not None:
                self.toolbar_3d = NavigationToolbar(self.canvas_3d, mpl_holder)
                self.toolbar_3d.setMaximumHeight(25)
                self.toolbar_3d.setStyleSheet(
                    "QToolBar { background:#FFFFFF; border:0px; spacing:1px; } "
                    "QToolButton { padding:1px; margin:0px; }"
                )
                mpl_layout.addWidget(self.toolbar_3d)
            mpl_layout.addWidget(self.canvas_3d, 1)
            self._three_d_stack_index = self.stack.addWidget(mpl_holder)
            # Keep a software-only 3D preview permanently available.  If a future
            # Matplotlib/backend incompatibility occurs, the user still gets a
            # usable scientific view instead of an application-level exception.
            self._fallback_stack_index = self.stack.addWidget(self.plot_3d_fallback)
        elif gl is not None and _USE_NATIVE_OPENGL_3D:
            self._three_d_backend = "opengl"
            try:
                self.view_3d = gl.GLViewWidget()
                self.view_3d.setBackgroundColor((255, 255, 255, 255))
                self._three_d_stack_index = self.stack.addWidget(self.view_3d)
                self._fallback_stack_index = self.stack.addWidget(self.plot_3d_fallback)
            except Exception:
                self.view_3d = None
                self._three_d_backend = "projected"
                self._fallback_stack_index = self.stack.addWidget(self.plot_3d_fallback)
                self._three_d_stack_index = self._fallback_stack_index
        else:
            self._fallback_stack_index = self.stack.addWidget(self.plot_3d_fallback)
            self._three_d_stack_index = self._fallback_stack_index
        root.addWidget(self.stack, 1)
        self.value_colorbar = PaletteColorBar(self)
        self.value_colorbar.set_state(0.0, 1.0, self._palette_name, label="Scientific value")
        root.addWidget(self.value_colorbar)

        self.status = QLabel("No dataset loaded")
        self.status.setObjectName("spatialStatus")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    @staticmethod
    def _prepare_plot(plot: pg.PlotWidget) -> None:
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.16)
        try:
            plot.getPlotItem().layout.setContentsMargins(5, 5, 5, 5)
            font = QFont("Arial", 7)
            plot.getAxis("left").setStyle(tickFont=font)
            plot.getAxis("bottom").setStyle(tickFont=font)
        except Exception:
            pass

    def set_palette(self, palette_name: str) -> None:
        self._palette_name = str(palette_name or DEFAULT_PALETTE)
        if hasattr(self, "palette_selector") and self.palette_selector.currentText() != self._palette_name:
            self.palette_selector.setCurrentText(self._palette_name)
        self._render()

    def set_mode(self, mode: str) -> None:
        target = str(mode or "2d").lower()
        if target.startswith("3"):
            target = "3d_spatial" if "relief" not in target else "3d_relief"
        index = self.mode_combo.findData(target)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        else:
            self._render()

    def set_data(
        self,
        x: np.ndarray,
        y: np.ndarray,
        values: np.ndarray,
        *,
        z: np.ndarray | None = None,
        title: str = "Dataset",
        value_label: str = "Value",
        value_units: str = "",
        coordinate_label: str = "Survey coordinates",
        allow_surface: bool = True,
    ) -> None:
        x_arr, y_arr, z_arr, v_arr = finite_xyzv(x, y, values, z)
        self._payload = _SpatialPayload(
            x_arr, y_arr, z_arr, v_arr, str(title), str(value_label), str(value_units),
            str(coordinate_label), bool(allow_surface),
        )
        self._render()

    def clear(self, message: str = "No dataset loaded") -> None:
        self._payload = None
        self.plot_2d.clear()
        self.plot_3d_fallback.clear()
        self._clear_3d()
        if self.figure_3d is not None:
            self.figure_3d.clear()
            if self.canvas_3d is not None:
                self.canvas_3d.draw_idle()
        self.status.setText(message)

    def _render(self) -> None:
        payload = self._payload
        if payload is None or payload.values.size == 0:
            self.clear("No finite spatial observations are available for 2D/3D display.")
            return
        finite_values = payload.values[np.isfinite(payload.values)]
        if finite_values.size:
            self.value_colorbar.set_state(
                float(np.nanmin(finite_values)),
                float(np.nanmax(finite_values)),
                self._palette_name,
                unit=payload.value_units,
                label=payload.value_label,
            )
        mode = str(self.mode_combo.currentData() or "2d")
        self._last_mode = mode
        if mode == "2d":
            self.stack.setCurrentIndex(0)
            self._render_2d(payload)
        else:
            if self._three_d_stack_index >= 0:
                self.stack.setCurrentIndex(self._three_d_stack_index)
            self._render_3d(payload, relief=(mode == "3d_relief"))

    @staticmethod
    def _finite_span(values: np.ndarray) -> float:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size < 2:
            return 0.0
        return float(np.nanmax(finite) - np.nanmin(finite))

    @staticmethod
    def _finite_median(values: np.ndarray, default: float = 0.0) -> float:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            return default
        return float(np.nanmedian(finite))

    def _fit_view(self) -> None:
        self._zoom_factor = 1.0
        self._render()

    def _set_view_preset(self, preset: str) -> None:
        self._view_preset = str(preset or "oblique")
        if self._last_mode == "2d":
            target = self.mode_combo.findData("3d_spatial")
            if target >= 0:
                self.mode_combo.setCurrentIndex(target)
                return
        self._render()

    def _zoom_3d(self, factor: float) -> None:
        self._zoom_factor = float(np.clip(self._zoom_factor * float(factor), 0.22, 4.0))
        if self._last_mode == "2d":
            target = self.mode_combo.findData("3d_spatial")
            if target >= 0:
                self.mode_combo.setCurrentIndex(target)
                return
        self._render()

    def _on_mpl_scroll(self, event) -> None:
        if self._last_mode == "2d":
            return
        step = getattr(event, "step", 0)
        self._zoom_3d(0.86 if step and step > 0 else 1.16)

    def _zoomed_limits(self, limits: tuple[float, float]) -> tuple[float, float]:
        lo, hi = float(limits[0]), float(limits[1])
        centre = (lo + hi) * 0.5
        half = max((hi - lo) * 0.5 * self._zoom_factor, 1e-9)
        return centre - half, centre + half

    def _profile_mode(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> bool:
        x_span = self._finite_span(x)
        y_span = self._finite_span(y)
        z_span = self._finite_span(z)
        return (x_span > 0.0 and z_span > 0.0 and y_span <= max(x_span, 1.0) * 0.06)

    def _render_2d(self, payload: _SpatialPayload) -> None:
        self.plot_2d.clear()
        idx = deterministic_decimation_indices(payload.values.size, 35000)
        x = payload.x[idx].astype(float)
        y = payload.y[idx].astype(float)
        z = payload.z[idx].astype(float)
        values = payload.values[idx].astype(float)
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(values)
        if not np.any(finite):
            self.status.setText("No finite observations available for 2D display.")
            return
        x, y, z, values = x[finite], y[finite], z[finite], values[finite]

        profile_mode = self._profile_mode(x, y, z)
        if profile_mode:
            plot_x = x - self._finite_median(x)
            plot_y = z
            bottom_label = "Profile / pseudo-X coordinate"
            left_label = "Elevation / negative pseudodepth"
            title_suffix = "2D pseudosection"
        else:
            plot_x = x
            plot_y = y
            bottom_label = "X / Easting / Longitude"
            left_label = "Y / Northing / Latitude"
            title_suffix = "2D map"

        normalized = normalize_robust(values)
        try:
            rgba = palette_rgba_array(normalized, self._palette_name)
            colors = [QColor(int(r), int(g), int(b), int(a)) for r, g, b, a in rgba]
            point_size = 7 if values.size <= 3000 else (5 if values.size <= 20000 else 3)
            spots = [
                {"pos": (float(px), float(py)), "brush": color, "pen": pg.mkPen("#FFFFFF", width=0.25), "size": point_size}
                for px, py, color in zip(plot_x, plot_y, colors)
            ]
            self.plot_2d.addItem(pg.ScatterPlotItem(spots=spots))
        except Exception:
            self.plot_2d.addItem(pg.ScatterPlotItem(x=plot_x, y=plot_y, size=5, pen=None))

        if profile_mode and plot_x.size > 2:
            try:
                order = np.argsort(plot_x)
                self.plot_2d.plot(plot_x[order], plot_y[order], pen=pg.mkPen("#A7B8C5", width=0.7))
            except Exception:
                pass

        self.plot_2d.setLabel("bottom", bottom_label)
        self.plot_2d.setLabel("left", left_label)
        self.plot_2d.setTitle(f"{payload.title} — {title_suffix} coloured by {payload.value_label}")
        self.plot_2d.enableAutoRange()
        self.status.setText(
            f"{title_suffix} • {payload.values.size:,} finite observations • colour = {payload.value_label}"
            f"{(' (' + payload.value_units + ')') if payload.value_units else ''} • {payload.coordinate_label}."
        )

    def _clear_3d(self) -> None:
        if self.view_3d is None:
            return
        for item in list(getattr(self.view_3d, "items", [])):
            try:
                self.view_3d.removeItem(item)
            except Exception:
                pass

    @staticmethod
    def _project_isometric(x0: np.ndarray, y0: np.ndarray, z0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        span_xy = max(float(np.nanmax(np.ptp(x0))) if x0.size else 1.0, float(np.nanmax(np.ptp(y0))) if y0.size else 1.0, 1.0)
        z_range = float(np.nanmax(z0) - np.nanmin(z0)) if z0.size else 0.0
        if not np.isfinite(z_range) or z_range <= 0:
            z_scaled = np.zeros_like(z0, dtype=float)
        else:
            z_scaled = (z0 - float(np.nanmedian(z0))) * (0.34 * span_xy / z_range)
        xp = x0 + 0.50 * y0
        yp = 0.28 * y0 - z_scaled
        return xp, yp

    def _render_3d(self, payload: _SpatialPayload, *, relief: bool) -> None:
        if self._three_d_backend == "matplotlib" and self.canvas_3d is not None and self.figure_3d is not None:
            try:
                if self._three_d_stack_index >= 0:
                    self.stack.setCurrentIndex(self._three_d_stack_index)
                self._render_3d_matplotlib(payload, relief=relief)
                return
            except Exception as exc:
                # Graphics/backend/API differences must never crash the application.
                # Fall back to the software-projected scientific preview and keep
                # the exact cause in the application log for diagnostics.
                logger.exception("Matplotlib 3D rendering failed; using projected fallback")
                if self._fallback_stack_index >= 0:
                    self.stack.setCurrentIndex(self._fallback_stack_index)
                self._render_3d_fallback(
                    payload, relief=relief,
                    note=f"Matplotlib 3D fallback: {type(exc).__name__}: {exc}",
                )
                return
        if self._three_d_backend != "opengl" or self.view_3d is None or gl is None or not _USE_NATIVE_OPENGL_3D:
            if self._fallback_stack_index >= 0:
                self.stack.setCurrentIndex(self._fallback_stack_index)
            self._render_3d_fallback(payload, relief=relief)
            return
        try:
            if self._three_d_stack_index >= 0:
                self.stack.setCurrentIndex(self._three_d_stack_index)
            self._render_3d_opengl(payload, relief=relief)
        except Exception as exc:
            logger.exception("Native OpenGL 3D rendering failed; using projected fallback")
            if self._fallback_stack_index >= 0:
                self.stack.setCurrentIndex(self._fallback_stack_index)
            self._render_3d_fallback(payload, relief=relief, note=f"Native OpenGL fallback: {exc}")

    @staticmethod
    def _mpl_colormap(name: str = "viridis"):
        """Return a Matplotlib colormap across old and new Matplotlib APIs.

        Matplotlib's public colormap registry moved from ``matplotlib.cm.get_cmap``
        to ``matplotlib.colormaps``.  Some recent builds no longer expose the old
        function, which previously caused every 3D redraw/zoom/preset action to
        raise an AttributeError.
        """
        registry = getattr(mpl, "colormaps", None) if mpl is not None else None
        if registry is not None:
            try:
                return registry.get_cmap(str(name))
            except Exception:
                try:
                    return registry[str(name)]
                except Exception:
                    pass
        getter = getattr(cm, "get_cmap", None) if cm is not None else None
        if callable(getter):
            try:
                return getter(str(name))
            except Exception:
                pass
        return None

    @staticmethod
    def _nice_range(values: np.ndarray, pad_fraction: float = 0.05) -> tuple[float, float]:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            return -1.0, 1.0
        lo = float(np.nanmin(finite))
        hi = float(np.nanmax(finite))
        if not np.isfinite(lo) or not np.isfinite(hi):
            return -1.0, 1.0
        if abs(hi - lo) <= 1e-12:
            pad = max(abs(lo) * 0.06, 1.0)
            return lo - pad, hi + pad
        pad = (hi - lo) * pad_fraction
        return lo - pad, hi + pad

    @staticmethod
    def _decimated_arrays(payload: _SpatialPayload, maximum: int = 45000) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        idx = deterministic_decimation_indices(payload.values.size, maximum)
        x = payload.x[idx].astype(float)
        y = payload.y[idx].astype(float)
        z = payload.z[idx].astype(float)
        values = payload.values[idx].astype(float)
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(values)
        return x[finite], y[finite], z[finite], values[finite]

    def _matplotlib_palette(self):
        if ListedColormap is None:
            return self._mpl_colormap("viridis")
        rgb = palette_rgb_array(self._palette_name, 256).astype(float) / 255.0
        return ListedColormap(rgb, name=f"tgpassure_{self._palette_name.replace(' ', '_')}")

    def _render_3d_matplotlib(self, payload: _SpatialPayload, *, relief: bool) -> None:
        x, y, z_physical, values = self._decimated_arrays(payload, 52000)
        self.figure_3d.clear()
        if values.size == 0:
            ax = self.figure_3d.add_subplot(111)
            ax.text(0.5, 0.5, "No finite 3D values to display", ha="center", va="center", color="#5A6B78")
            ax.set_axis_off()
            self.canvas_3d.draw_idle()
            return

        cx = self._finite_median(x)
        cy = self._finite_median(y)
        x0 = x - cx
        y0 = y - cy
        horizontal_span = max(self._finite_span(x0), self._finite_span(y0), 1.0)
        if relief:
            z0 = value_relief(values, horizontal_span, 0.55)
            z_label = "Value relief"
            z_note = "display-only robust value relief, not inversion depth"
        else:
            z_ref = self._finite_median(z_physical)
            z0 = np.where(np.isfinite(z_physical), z_physical - z_ref, 0.0)
            z_label = "Elevation / depth"
            z_note = "physical elevation or electrical pseudodepth where available"

        profile_mode = self._profile_mode(x0, y0, z0)
        x_span = max(self._finite_span(x0), 1.0)
        y_span_source = self._finite_span(y0)
        z_span = max(self._finite_span(z0), 1.0)
        display_y_note = ""
        if profile_mode:
            # ERT/IP/VES datasets are commonly a single traverse. A true XY/Z plot
            # becomes a thin line, so render a professional 3D pseudosection curtain:
            # X and Z remain data coordinates; Y is only a narrow visual corridor for
            # rotation, zoom and depth perception.
            y_half = max(x_span * 0.115, z_span * 0.75, 1.0)
            y_plot = np.zeros_like(values, dtype=float)
            ylim = (-y_half, y_half)
            display_y_note = " • single-line data shown as a rotatable 3D pseudosection curtain"
        else:
            y_plot = y0
            y_half = max(y_span_source * 0.5, 1.0)
            ylim = self._nice_range(y_plot, 0.055)

        ax = self.figure_3d.add_subplot(111, projection="3d", facecolor="white")
        try:
            # Wider plotting area than the previous build; colorbar remains outside.
            ax.set_position([0.035, 0.055, 0.805, 0.885])
            ax.grid(True, alpha=0.26)
            for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
                pane.set_facecolor((1.0, 1.0, 1.0, 1.0))
                pane.set_edgecolor((0.76, 0.83, 0.88, 1.0))
        except Exception:
            pass

        norm = None
        cmap_obj = None
        if Normalize is not None and cm is not None:
            finite_values = values[np.isfinite(values)]
            vmin, vmax = (float(np.nanmin(finite_values)), float(np.nanmax(finite_values))) if finite_values.size else (0.0, 1.0)
            if abs(vmax - vmin) <= 1e-12:
                vmin -= 0.5
                vmax += 0.5
            norm = Normalize(vmin=vmin, vmax=vmax)
            cmap_obj = self._matplotlib_palette()

        # Draw a curtain/surface first so the 3D structure is visible, then draw
        # measurement dots over it so individual readings are still inspectable.
        if profile_mode and Triangulation is not None and values.size >= 8 and cmap_obj is not None and norm is not None:
            try:
                tri = Triangulation(x0, z0)
                # Remove very flat/huge triangles where possible to keep field lines clean.
                triangles = tri.triangles
                if triangles.size:
                    mean_colours = cmap_obj(norm(np.nanmean(values[triangles], axis=1)))
                    surf = ax.plot_trisurf(
                        x0, y_plot, z0, triangles=triangles,
                        linewidth=0.18, edgecolor=(0.86, 0.91, 0.94, 0.52),
                        shade=False, alpha=0.62, antialiased=True,
                    )
                    surf.set_facecolors(mean_colours)
                    # Add front/back reference ribbons to make the plane readable when rotated.
                    order = np.lexsort((z0, x0))
                    for yy in (-y_half * 0.92, y_half * 0.92):
                        ax.plot(x0[order], np.full_like(x0[order], yy), z0[order], color="#C7D4DD", linewidth=0.55, alpha=0.50)
            except Exception:
                pass
        elif (not profile_mode) and payload.allow_surface and values.size >= 20:
            try:
                ax.plot_trisurf(x0, y_plot, z0, cmap=cmap_obj, alpha=0.18, linewidth=0.08, antialiased=True)
            except Exception:
                pass

        point_size = 42 if values.size <= 750 else (28 if values.size <= 3000 else (15 if values.size <= 12000 else 7))
        scatter = ax.scatter(
            x0, y_plot, z0, c=values, cmap=cmap_obj, s=point_size,
            depthshade=False, edgecolors="#FFFFFF", linewidths=0.16, alpha=0.98, marker="o",
        )

        # Add profile trace lines/depth ribs for readability.
        if profile_mode and values.size > 2:
            try:
                order = np.lexsort((z0, x0))
                ax.plot(x0[order], y_plot[order], z0[order], color="#738A99", linewidth=0.75, alpha=0.62)
                quantiles = np.unique(np.nanpercentile(x0, [10, 25, 50, 75, 90]))
                zmin, zmax = self._nice_range(z0, 0.04)
                for qx in quantiles:
                    ax.plot([qx, qx], [-y_half * 0.70, y_half * 0.70], [zmin, zmax], color="#D4E0E7", linewidth=0.45, alpha=0.46)
            except Exception:
                pass

        xlim = self._zoomed_limits(self._nice_range(x0, 0.050))
        ylim = self._zoomed_limits(ylim)
        zlim = self._zoomed_limits(self._nice_range(z0, 0.075))
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_zlim(*zlim)

        try:
            if profile_mode:
                ax.set_box_aspect((4.8, 1.35, 1.55))
            else:
                ax.set_box_aspect((3.2, 2.9, 1.25))
        except Exception:
            pass

        # View presets make the 3D display useful without needing manual camera work.
        preset = self._view_preset
        if preset == "top":
            ax.view_init(elev=87, azim=-90)
        elif preset == "side":
            ax.view_init(elev=9 if profile_mode else 16, azim=-90)
        else:
            ax.view_init(elev=25 if profile_mode else 30, azim=-63 if profile_mode else -46)
        try:
            ax.set_proj_type("persp", focal_length=0.72)
        except Exception:
            pass
        try:
            ax.margins(x=0.0, y=0.0, z=0.0)
        except Exception:
            pass

        cax = self.figure_3d.add_axes([0.875, 0.18, 0.014, 0.62])
        cbar = self.figure_3d.colorbar(scatter, cax=cax)
        label = payload.value_label if not payload.value_units else f"{payload.value_label} ({payload.value_units})"
        cbar.set_label(label, fontsize=7.5)
        cbar.ax.tick_params(labelsize=7)

        title = f"{payload.title} — {'3D value relief' if relief else 'interactive 3D QC view'}"
        ax.set_title(title, fontsize=10.2, color="#314B5A", pad=3)
        ax.set_xlabel("X / profile coordinate", fontsize=7.4, labelpad=2)
        ax.set_ylabel("Y / line corridor", fontsize=7.4, labelpad=2)
        ax.set_zlabel(z_label, fontsize=7.4, labelpad=2)
        ax.tick_params(labelsize=6.7, colors="#647986", pad=0)
        try:
            # Keep axis labels from dominating the view.
            ax.xaxis.label.set_color("#405969")
            ax.yaxis.label.set_color("#405969")
            ax.zaxis.label.set_color("#405969")
        except Exception:
            pass

        self.canvas_3d.draw_idle()
        self.status.setText(
            f"Interactive 3D view • {payload.values.size:,} observations • drag plot to rotate, mouse wheel/+/− to zoom, toolbar pan/save • "
            f"colour = {payload.value_label} • Z = {z_note}{display_y_note}. Origin centred near ({cx:.3f}, {cy:.3f})."
        )

    def _render_3d_fallback(self, payload: _SpatialPayload, *, relief: bool, note: str | None = None) -> None:
        self.plot_3d_fallback.clear()
        x, y, z_physical, values = self._decimated_arrays(payload, 40000)
        if values.size == 0:
            self.status.setText("No finite 3D values to display.")
            return
        cx, cy = self._finite_median(x), self._finite_median(y)
        x0, y0 = x - cx, y - cy
        horizontal_span = max(self._finite_span(x0), self._finite_span(y0), 1.0)
        if relief:
            z0 = value_relief(values, horizontal_span, 0.30)
            z_note = "display-only robust value relief, not inversion depth"
        else:
            z_ref = self._finite_median(z_physical)
            z0 = np.where(np.isfinite(z_physical), z_physical - z_ref, 0.0)
            z_note = "physical/recorded elevation where available"
        xp, yp = self._project_isometric(x0, y0, z0)
        normalized = normalize_robust(values)
        try:
            rgba = palette_rgba_array(normalized, self._palette_name)
            colors = [QColor(int(r), int(g), int(b), int(a)) for r, g, b, a in rgba]
            point_size = 7 if values.size <= 3000 else (5 if values.size <= 20000 else 3)
            spots = [
                {"pos": (float(px), float(py)), "brush": color, "pen": pg.mkPen("#FFFFFF", width=0.25), "size": point_size}
                for px, py, color in zip(xp, yp, colors)
            ]
            self.plot_3d_fallback.addItem(pg.ScatterPlotItem(spots=spots))
        except Exception:
            self.plot_3d_fallback.addItem(pg.ScatterPlotItem(x=xp, y=yp, size=5, pen=None))
        axis_pen = pg.mkPen("#8AA0B2", width=1)
        try:
            self.plot_3d_fallback.plot([0, horizontal_span * 0.26], [0, 0], pen=axis_pen)
            self.plot_3d_fallback.plot([0, 0], [0, horizontal_span * 0.16], pen=axis_pen)
            self.plot_3d_fallback.plot([0, -horizontal_span * 0.10], [0, -horizontal_span * 0.18], pen=axis_pen)
        except Exception:
            pass
        self.plot_3d_fallback.setLabel("bottom", "Projected X / Y / Z")
        self.plot_3d_fallback.setLabel("left", "Isometric display")
        self.plot_3d_fallback.setTitle(f"{payload.title} — safe 3D preview coloured by {payload.value_label}")
        self.plot_3d_fallback.enableAutoRange()
        extra = f" • {note}" if note else ""
        self.status.setText(
            f"Safe 3D preview • {payload.values.size:,} observations • colour = {payload.value_label} • Z = {z_note}. "
            f"Origin centred near ({cx:.3f}, {cy:.3f}).{extra}"
        )

    def _render_3d_opengl(self, payload: _SpatialPayload, *, relief: bool) -> None:
        self._clear_3d()
        x, y, z_physical, values = self._decimated_arrays(payload, 50000)
        if values.size == 0:
            self.status.setText("No finite 3D values to display.")
            return
        cx, cy = self._finite_median(x), self._finite_median(y)
        x0, y0 = x - cx, y - cy
        horizontal_span = max(self._finite_span(x0), self._finite_span(y0), 1.0)
        if relief:
            z0 = value_relief(values, horizontal_span, 0.22)
            z_note = "display-only robust value relief"
        else:
            z_ref = self._finite_median(z_physical)
            z0 = np.where(np.isfinite(z_physical), z_physical - z_ref, 0.0)
            z_note = "physical/recorded elevation where available"
        normalized = normalize_robust(values)
        try:
            colors = palette_rgba_array(normalized, self._palette_name).astype(float) / 255.0
        except Exception:
            colors = np.c_[normalized, 1.0 - normalized, np.full_like(normalized, 0.5), np.ones_like(normalized)]
        positions = np.column_stack((x0, y0, z0))
        scatter = gl.GLScatterPlotItem(pos=positions, color=colors, size=5.0, pxMode=True)
        self.view_3d.addItem(scatter)
        if payload.allow_surface and not relief:
            surface = grid_scattered_surface(x0, y0, z0, values, max_cells=70)
            if surface is not None:
                norm_grid = normalize_robust(surface.values)
                try:
                    surf_colors = palette_rgba_array(norm_grid, self._palette_name).astype(float) / 255.0
                    surf_colors[..., 3] = np.where(surface.inside_hull, 0.68, 0.0)
                    mesh = gl.GLSurfacePlotItem(x=surface.x, y=surface.y, z=surface.z, colors=surf_colors, shader="shaded", smooth=False, computeNormals=True)
                    self.view_3d.addItem(mesh)
                except Exception:
                    pass
        grid = gl.GLGridItem()
        grid.setSize(x=horizontal_span * 1.08, y=horizontal_span * 1.08)
        grid.setSpacing(x=max(horizontal_span / 10.0, 1e-6), y=max(horizontal_span / 10.0, 1e-6))
        self.view_3d.addItem(grid)
        self.view_3d.opts["distance"] = horizontal_span * 1.18
        self.view_3d.opts["elevation"] = 30
        self.view_3d.opts["azimuth"] = 42
        self.view_3d.opts["center"] = pg.Vector(0, 0, self._finite_median(z0))
        self.view_3d.setBackgroundColor((255, 255, 255, 255))
        self.view_3d.update()
        self.status.setText(
            f"Native OpenGL 3D view • {payload.values.size:,} observations • colour = {payload.value_label} • Z = {z_note}. "
            f"Origin centred near ({cx:.3f}, {cy:.3f})."
        )
