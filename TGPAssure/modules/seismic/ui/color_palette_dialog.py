from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

COLOR_PALETTES = {'Seismic': ['#122452', '#1260A0', '#13A6B9', '#FFD54F', '#DA3C2D'],
 'Seismic Blue-White-Red': ['#191970', '#1E90FF', '#F0F8FF', '#FF6347', '#8B0000'],
 'Viridis': ['#440154', '#31688E', '#35B779', '#FDE725'],
 'Grayscale': ['#000000', '#404040', '#808080', '#BFBFBF', '#FFFFFF'],
 'Blue Ice': ['#071A2F', '#0F4C81', '#1FA2FF', '#A7F3D0', '#FFFFFF'],
 'Copper Heat': ['#1C1210', '#7C2D12', '#EA580C', '#FDBA74', '#FFF7ED'],
 'Rainbow': ['#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF', '#8B00FF'],
 'Hot': ['#000000', '#7F0000', '#FF0000', '#FF7F00', '#FFFF00', '#FFFFFF'],
 'Cool': ['#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF0000'],
 'Jet': ['#00008F', '#0000FF', '#0080FF', '#00FFFF', '#80FF80', '#FFFF00', '#FF8000', '#FF0000', '#800000'],
 'Ocean': ['#000040', '#000080', '#0080C0', '#00C0FF', '#80E0FF', '#FFFFFF'],
 'Terrain': ['#004400', '#008000', '#90C090', '#C0C080', '#E0E080', '#FFFFFF'],
 'Spectral': ['#0000FF',
              '#0080FF',
              '#00FFFF',
              '#00FF80',
              '#80FF00',
              '#FFFF00',
              '#FF8000',
              '#FF0080',
              '#FF0000'],
 'NEO (Night Earth)': ['#000000',
                       '#001020',
                       '#004060',
                       '#0080A0',
                       '#00C0E0',
                       '#FFFFFF',
                       '#FFE080',
                       '#FFA040',
                       '#FF4000'],
 'Volumetric Picker': ['#000000',
                       '#000080',
                       '#0040C0',
                       '#0080FF',
                       '#80C0FF',
                       '#FFFFFF',
                       '#FFC080',
                       '#FF8000',
                       '#C04000',
                       '#800000'],
 'Seismic Dip Azimuth': ['#FF0000',
                         '#FF8000',
                         '#FFFF00',
                         '#00FF00',
                         '#00FFFF',
                         '#0080FF',
                         '#FF00FF',
                         '#FF0080'],
 'SeismicRWB': ['#0000FF', '#0080FF', '#00FFFF', '#FFFFFF', '#FFFF00', '#FF8000', '#FF0000'],
 'Red Blue Green': ['#FF0000', '#FF80FF', '#FFFFFF', '#80FFFF', '#00FF00'],
 'Green Blue Red': ['#00FF00', '#80FFFF', '#FFFFFF', '#FF80FF', '#FF0000'],
 'Polarity': ['#0000FF', '#0080FF', '#FFFFFF', '#FF8000', '#FF0000'],
 'Semblance': ['#000000',
               '#004080',
               '#0080FF',
               '#00FFFF',
               '#00FF80',
               '#80FF00',
               '#FFFF00',
               '#FF8000',
               '#FF0000'],
 'Reflection Strength': ['#FFFFFF', '#80FF80', '#00FF00', '#008000', '#004000', '#000000'],
 'Variance': ['#000000', '#003F5C', '#7A5195', '#EF5675', '#FF7C43', '#F9A93D', '#FFD166'],
 'Local Flatness': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Structural Lows': ['#000000', '#001040', '#003080', '#0060C0', '#00A0FF', '#80D0FF', '#FFFFFF'],
 'Thickness': ['#FFFFFF', '#FFE0A0', '#FFC040', '#FF8000', '#A04000', '#400000'],
 'Uncertainty': ['#FFFFFF', '#C0E0FF', '#80C0FF', '#4080FF', '#0040FF', '#0000A0'],
 'Velocity': ['#000000',
              '#000040',
              '#000080',
              '#0040C0',
              '#0080FF',
              '#00FFFF',
              '#80FF80',
              '#FFFF00',
              '#FF8000',
              '#FF0000'],
 'Resistivity': ['#000000',
                 '#800000',
                 '#FF0000',
                 '#FF8000',
                 '#FFFF00',
                 '#80FF80',
                 '#00FFFF',
                 '#0080FF',
                 '#0000FF',
                 '#400080'],
 'Permeability': ['#FFFFFF', '#FFE0C0', '#FFA080', '#FF6040', '#D02000', '#800000'],
 'Water Saturation': ['#000000', '#000080', '#0040C0', '#0080FF', '#40C0FF', '#80E0FF', '#FFFFFF'],
 'Vitrinite Reflectance': ['#000000', '#003000', '#006000', '#00A000', '#40C040', '#80E080', '#FFFFFF'],
 'Gold': ['#000000', '#402000', '#804000', '#BF8000', '#FFBF00', '#FFFFFF'],
 'Gold White Blue': ['#000000',
                     '#402000',
                     '#804000',
                     '#BF8000',
                     '#FFBF00',
                     '#FFFFFF',
                     '#80C0FF',
                     '#0080FF',
                     '#004080'],
 'White Blue': ['#FFFFFF', '#80C0FF', '#0080FF', '#004080', '#000080'],
 'White Blue Green': ['#FFFFFF', '#80C0FF', '#0080FF', '#00A0A0', '#008000'],
 'White Grey Blue': ['#FFFFFF', '#C0C0C0', '#808080', '#4080C0', '#004080'],
 'White Red': ['#FFFFFF', '#FFC0C0', '#FF8080', '#FF4040', '#FF0000'],
 'White Yellow': ['#FFFFFF', '#FFFFC0', '#FFFF80', '#FFFF00', '#BF8000'],
 'Red Yellow Green': ['#FF0000', '#FF8000', '#FFFF00', '#80FF00', '#00FF00'],
 'Red White Blue': ['#FF0000', '#FF8080', '#FFFFFF', '#8080FF', '#0000FF'],
 'Red White Blue (Reverse)': ['#0000FF', '#8080FF', '#FFFFFF', '#FF8080', '#FF0000'],
 'Red White Blue (Blocky)': ['#FF0000',
                             '#FF4444',
                             '#FF8888',
                             '#FFCCCC',
                             '#FFFFFF',
                             '#CCCCFF',
                             '#8888FF',
                             '#4444FF',
                             '#0000FF'],
 'Blue White Red': ['#0000FF', '#8080FF', '#FFFFFF', '#FF8080', '#FF0000'],
 'Blue White Red (Blocky)': ['#0000FF',
                             '#4444FF',
                             '#8888FF',
                             '#CCCCFF',
                             '#FFFFFF',
                             '#FFCCCC',
                             '#FF8888',
                             '#FF4444',
                             '#FF0000'],
 'White Black Red': ['#FFFFFF', '#C0C0C0', '#808080', '#404040', '#800000', '#FF0000'],
 'White Black Red (Anti)': ['#FFFFFF', '#C0C0C0', '#808080', '#404040', '#800000', '#FF0000', '#FF8000'],
 'Red White Black': ['#FF0000', '#FF8080', '#FFFFFF', '#808080', '#000000'],
 'Green Yellow Red': ['#00FF00', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Green Blue Brown': ['#004000', '#008000', '#00C000', '#40A0A0', '#808080', '#A06040', '#804020'],
 'Purple Blue Green': ['#800080', '#4000C0', '#0080FF', '#00C0C0', '#00FF00'],
 'Purple Blue Green (Reverse)': ['#00FF00', '#00C0C0', '#0080FF', '#4000C0', '#800080'],
 'Purple Green Red': ['#800080', '#4000C0', '#00C0A0', '#80FF80', '#FFFF00', '#FF8000', '#FF0000'],
 'YellowFMS': ['#000000',
               '#004000',
               '#008000',
               '#00C000',
               '#C0C000',
               '#FFFF00',
               '#FFC000',
               '#FF8000',
               '#FF4000',
               '#FF0000'],
 'YellowFMS-GR': ['#000000',
                  '#004000',
                  '#008000',
                  '#00C000',
                  '#C0C000',
                  '#FFFF00',
                  '#FFC000',
                  '#FF8000',
                  '#FF4000',
                  '#FF0000',
                  '#FF0080',
                  '#FF00FF'],
 'YellowFMS-PEF': ['#FFFFFF', '#FFFF80', '#FFFF00', '#FFC000', '#FF8000', '#FF4000', '#FF0000', '#800000'],
 'YellowFMS-R': ['#FFFFFF', '#FFE0E0', '#FFC0C0', '#FF8080', '#FF4040', '#FF0000', '#800000'],
 'YellowFMS-T': ['#FFFFFF', '#FFE0C0', '#FFC080', '#FF8040', '#FF4000', '#800000'],
 'GrayLU': ['#000000',
            '#202020',
            '#404040',
            '#606060',
            '#808080',
            '#A0A0A0',
            '#C0C0C0',
            '#E0E0E0',
            '#FFFFFF'],
 'SunbowLU': ['#000000', '#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF0000', '#FFFFFF'],
 'RainbowLU': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Sunny Side Up': ['#000040',
                   '#000080',
                   '#0040C0',
                   '#0080FF',
                   '#40C0FF',
                   '#80FFFF',
                   '#FFFF80',
                   '#FFE080',
                   '#FFC040',
                   '#FF8000'],
 'Spectrum': ['#000000', '#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Log Rainbow': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Log VDL': ['#000000', '#004000', '#008000', '#00C000', '#C0C000', '#FFFF00', '#FF8000', '#FF0000'],
 'Log Sand & Shale': ['#FFE0A0',
                      '#FFD080',
                      '#FFC060',
                      '#FFA040',
                      '#FF8020',
                      '#C06020',
                      '#804020',
                      '#402010',
                      '#000000'],
 'Log Seismic': ['#0000FF', '#0080FF', '#00FFFF', '#FFFFFF', '#FFFF00', '#FF8000', '#FF0000'],
 'Map Blocked': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000']}


def palette_icon(colors: list[str] | None = None, size: int = 18) -> QIcon:
    """Create a small colour-table icon without external resources."""
    colors = colors or COLOR_PALETTES["Seismic"]
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    count = max(1, min(5, len(colors)))
    width = max(2, (size - 2) // count)
    for index in range(count):
        color = QColor(colors[index * len(colors) // count])
        painter.fillRect(1 + index * width, 1, width + 1, size - 2, color)
    painter.setPen(QColor("#263238"))
    painter.drawRoundedRect(1, 1, size - 3, size - 3, 2, 2)
    painter.end()
    return QIcon(pixmap)


class _PaletteButton(QPushButton):
    def __init__(self, name: str, colors: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.palette_name = name
        self.setObjectName("paletteItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(31)
        self.setMaximumHeight(33)
        self.setText(name)
        self.setIcon(palette_icon(colors, 17))
        self.setIconSize(QSize(28, 18))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class ColorPaletteDialog(QDialog):
    """Dense multi-column colour-table selector styled after the supplied reference."""

    palette_selected = Signal(str)

    def __init__(self, current_palette: str = "Seismic", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select color table")
        self.setMinimumSize(860, 520)
        self.resize(1080, 650)
        self._selected_palette = current_palette if current_palette in COLOR_PALETTES else "Seismic"
        self._buttons: dict[str, _PaletteButton] = {}
        self._build_ui()
        self._populate()

    @property
    def selected_palette(self) -> str:
        return self._selected_palette

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog { background:#F2F2F2; font-family:Arial; font-size:9pt; }
            QLabel { color:#202020; background:transparent; }
            QComboBox, QLineEdit {
                background:#FFFFFF; border:1px solid #A0A0A0;
                padding:3px 6px; min-height:24px; color:#202020;
            }
            QCheckBox { color:#202020; }
            QScrollArea { background:#FFFFFF; border:1px solid #9A9A9A; }
            QPushButton#paletteItem {
                text-align:left; padding:2px 5px; margin:1px;
                border:1px solid transparent; background:#FFFFFF; color:#111111;
                font-family:Arial; font-size:8.5pt; font-weight:400;
            }
            QPushButton#paletteItem:hover {
                background:#EAF3FF; border:1px solid #8DB7E5;
            }
            QPushButton#paletteItem[selected="true"] {
                background:#DCEBFA; border:1px solid #5C8FBE; font-weight:700;
            }
            QDialogButtonBox QPushButton {
                min-width:78px; min-height:28px; padding:2px 12px; font-weight:700;
            }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("View:"))
        self.view_combo = QComboBox()
        self.view_combo.addItem("List")
        self.view_combo.setFixedWidth(205)
        top.addWidget(self.view_combo)
        self.group_check = QCheckBox("Group by folder")
        self.group_check.setEnabled(False)
        top.addWidget(self.group_check)
        top.addStretch(1)
        top.addWidget(QLabel("Name contains:"))
        self.search = QLineEdit()
        self.search.setFixedWidth(265)
        self.search.textChanged.connect(self._populate)
        top.addWidget(self.search)
        root.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(5, 5, 5, 5)
        self.grid.setHorizontalSpacing(1)
        self.grid.setVerticalSpacing(1)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        bottom.addWidget(self.buttons)
        root.addLayout(bottom)

    def _populate(self, *_args) -> None:
        query = self.search.text().strip().lower()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()

        names = [name for name in COLOR_PALETTES if not query or query in name.lower()]
        columns = 6
        for index, name in enumerate(names):
            button = _PaletteButton(name, COLOR_PALETTES[name])
            button.clicked.connect(lambda _checked=False, palette=name: self._select_palette(palette))
            self._buttons[name] = button
            row, column = divmod(index, columns)
            self.grid.addWidget(button, row, column)

        for column in range(columns):
            self.grid.setColumnStretch(column, 1)
        self._refresh_selection()

    def _select_palette(self, name: str) -> None:
        if name in COLOR_PALETTES:
            self._selected_palette = name
            self._refresh_selection()

    def _refresh_selection(self) -> None:
        for name, button in self._buttons.items():
            button.set_selected(name == self._selected_palette)

    def _accept(self) -> None:
        self.palette_selected.emit(self._selected_palette)
        self.accept()


def palette_to_rgb_array(name: str, samples: int = 256) -> np.ndarray:
    colors = COLOR_PALETTES.get(name, COLOR_PALETTES["Seismic"])
    rgb = np.array([[QColor(c).red(), QColor(c).green(), QColor(c).blue()] for c in colors], dtype=np.float64)
    if len(rgb) == 1:
        return np.repeat(rgb.astype(np.uint8), samples, axis=0)
    positions = np.linspace(0.0, 1.0, len(rgb))
    target = np.linspace(0.0, 1.0, samples)
    result = np.column_stack([np.interp(target, positions, rgb[:, channel]) for channel in range(3)])
    return np.clip(result, 0, 255).astype(np.uint8)
