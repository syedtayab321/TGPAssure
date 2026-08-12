from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QGuiApplication, QIcon, QLinearGradient, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget,
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


# ---------------------------------------------------------------------------
# Design tokens (steel-blue / white / gray with orange accent — matches the
# Petrel-style shell used elsewhere in the app)
# ---------------------------------------------------------------------------
STEEL_DARK = "#2C3E50"
STEEL = "#34506E"
STEEL_LIGHT = "#4A6FA5"
ACCENT = "#E8833A"
ACCENT_DARK = "#D06C22"
BG = "#F2F4F7"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E1E6ED"
TEXT_PRIMARY = "#22303F"
TEXT_MUTED = "#66758A"


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


class _GradientSwatch(QWidget):
    """Renders the full colour ramp as a smooth horizontal gradient bar."""

    def __init__(self, colors: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._colors = colors
        self.setMinimumHeight(28)
        self.setMaximumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)

        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        colors = self._colors
        if len(colors) == 1:
            gradient.setColorAt(0.0, QColor(colors[0]))
            gradient.setColorAt(1.0, QColor(colors[0]))
        else:
            step = 1.0 / (len(colors) - 1)
            for index, hex_color in enumerate(colors):
                gradient.setColorAt(min(1.0, index * step), QColor(hex_color))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 5, 5)

        painter.setPen(QColor(0, 0, 0, 28))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)
        painter.end()


class _PaletteCard(QFrame):
    """A clickable card showing a palette's gradient preview and name."""

    clicked = Signal(str)

    def __init__(self, name: str, colors: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.palette_name = name
        self.setObjectName("paletteCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{name}  ({len(colors)} stops)")
        self.setProperty("selected", "false")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(148)
        self.setFixedHeight(66)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 9)
        layout.setSpacing(6)

        self.swatch = _GradientSwatch(colors)
        layout.addWidget(self.swatch)

        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        self.name_label = QLabel(name)
        self.name_label.setObjectName("paletteName")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        fm = self.name_label.fontMetrics()
        self.name_label.setText(fm.elidedText(name, Qt.TextElideMode.ElideRight, 148))
        title_row.addWidget(self.name_label)

        self.check_label = QLabel("\u2713")
        self.check_label.setObjectName("checkLabel")
        self.check_label.setFixedWidth(14)
        self.check_label.setVisible(False)
        title_row.addWidget(self.check_label)

        layout.addLayout(title_row)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.check_label.setVisible(selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.palette_name)
        super().mousePressEvent(event)


class ColorPaletteDialog(QDialog):
    """Colour-table selector styled to match the app's steel-blue / orange design system."""

    palette_selected = Signal(str)

    def __init__(self, current_palette: str = "Seismic", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Color Table")
        self.setMinimumSize(760, 520)
        self.resize(940, 640)
        self._selected_palette = current_palette if current_palette in COLOR_PALETTES else "Seismic"
        self._cards: dict[str, _PaletteCard] = {}
        self._build_ui()
        self._populate()

    @property
    def selected_palette(self) -> str:
        return self._selected_palette

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG};
                font-family: 'Segoe UI', Arial;
                font-size: 9.5pt;
            }}
            QLabel {{ color: {TEXT_PRIMARY}; background: transparent; }}

            #headerBar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {STEEL_DARK}, stop:1 {STEEL_LIGHT});
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            #headerTitle {{ color: #FFFFFF; font-size: 14.5pt; font-weight: 700; }}
            #headerSubtitle {{ color: rgba(255,255,255,0.80); font-size: 8.5pt; }}

            #toolbarBar {{ background: transparent; }}
            QComboBox, QLineEdit {{
                background: {CARD_BG};
                border: 1px solid #C9D2DE;
                border-radius: 6px;
                padding: 4px 10px;
                min-height: 24px;
                color: {TEXT_PRIMARY};
            }}
            QComboBox:focus, QLineEdit:focus {{ border: 1px solid {STEEL_LIGHT}; }}
            QCheckBox {{ color: {TEXT_MUTED}; }}

            QScrollArea {{ background: transparent; border: none; }}
            #scrollContent {{ background: transparent; }}

            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{
                background: #C7D0DC; border-radius: 5px; min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #A8B7C9; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

            #paletteCard {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
            #paletteCard:hover {{
                border: 1px solid {STEEL_LIGHT};
                background: #F6F9FD;
            }}
            #paletteCard[selected="true"] {{
                border: 2px solid {ACCENT};
                background: #FFF6EE;
            }}
            #paletteName {{ color: {TEXT_PRIMARY}; font-size: 8.5pt; font-weight: 600; }}
            #checkLabel {{ color: {ACCENT_DARK}; font-weight: 800; font-size: 10pt; }}

            #footerBar {{ background: transparent; }}
            #selectionLabel {{ color: {TEXT_MUTED}; font-size: 8.5pt; }}
            #selectionLabel b {{ color: {TEXT_PRIMARY}; }}

            QDialogButtonBox QPushButton {{
                min-width: 88px; min-height: 30px;
                border-radius: 6px; padding: 4px 14px; font-weight: 600;
            }}
            #okButton {{
                background: {STEEL_LIGHT}; color: #FFFFFF; border: none;
            }}
            #okButton:hover {{ background: {STEEL}; }}
            #okButton:pressed {{ background: {STEEL_DARK}; }}
            #cancelButton {{
                background: {CARD_BG}; color: {TEXT_PRIMARY}; border: 1px solid #C9D2DE;
            }}
            #cancelButton:hover {{ background: #EBEFF4; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Header -----------------------------------------------------
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(64)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(2)
        title = QLabel("Select Color Table")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Choose a colour ramp to apply to the active display")
        subtitle.setObjectName("headerSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # ---- Body (margins give consistent breathing room) --------------
        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(QLabel("View:"))
        self.view_combo = QComboBox()
        self.view_combo.addItem("List")
        self.view_combo.setFixedWidth(180)
        toolbar.addWidget(self.view_combo)
        self.group_check = QCheckBox("Group by folder")
        self.group_check.setEnabled(False)
        toolbar.addWidget(self.group_check)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Name contains:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search palettes\u2026")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._populate)
        toolbar.addWidget(self.search)
        body.addLayout(toolbar)

        # Card grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("scrollContent")
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(2, 2, 10, 2)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        self.scroll.setWidget(content)
        body.addWidget(self.scroll, 1)

        root.addLayout(body)

        # ---- Footer -------------------------------------------------------
        footer = QFrame()
        footer.setObjectName("footerBar")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 12, 20, 18)
        footer_layout.setSpacing(10)

        self.selection_label = QLabel()
        self.selection_label.setObjectName("selectionLabel")
        footer_layout.addWidget(self.selection_label)
        footer_layout.addStretch(1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setObjectName("okButton")
        if cancel_btn is not None:
            cancel_btn.setObjectName("cancelButton")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        footer_layout.addWidget(self.buttons)

        root.addWidget(footer)

    # ------------------------------------------------------------------
    # Population / selection
    # ------------------------------------------------------------------
    def _populate(self, *_args) -> None:
        query = self.search.text().strip().lower()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards.clear()

        names = [name for name in COLOR_PALETTES if not query or query in name.lower()]
        columns = 4
        for index, name in enumerate(names):
            card = _PaletteCard(name, COLOR_PALETTES[name])
            card.clicked.connect(self._select_palette)
            self._cards[name] = card
            row, column = divmod(index, columns)
            self.grid.addWidget(card, row, column)

        for column in range(columns):
            self.grid.setColumnStretch(column, 1)
        self._refresh_selection()

    def _select_palette(self, name: str) -> None:
        if name in COLOR_PALETTES:
            self._selected_palette = name
            self._refresh_selection()

    def _refresh_selection(self) -> None:
        for name, card in self._cards.items():
            card.set_selected(name == self._selected_palette)
        self.selection_label.setText(f"Selected: <b>{self._selected_palette}</b>")

    def _accept(self) -> None:
        self.palette_selected.emit(self._selected_palette)
        self.accept()

    # ------------------------------------------------------------------
    # Centering — equal distance from left/right and top/bottom of screen
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        self._center_on_screen()

    def _center_on_screen(self) -> None:
        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else None
        if screen is None:
            screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        size = self.frameGeometry().size()
        x = available.x() + (available.width() - size.width()) // 2
        y = available.y() + (available.height() - size.height()) // 2
        self.move(max(available.x(), x), max(available.y(), y))


def palette_to_rgb_array(name: str, samples: int = 256) -> np.ndarray:
    colors = COLOR_PALETTES.get(name, COLOR_PALETTES["Seismic"])
    rgb = np.array([[QColor(c).red(), QColor(c).green(), QColor(c).blue()] for c in colors], dtype=np.float64)
    if len(rgb) == 1:
        return np.repeat(rgb.astype(np.uint8), samples, axis=0)
    positions = np.linspace(0.0, 1.0, len(rgb))
    target = np.linspace(0.0, 1.0, samples)
    result = np.column_stack([np.interp(target, positions, rgb[:, channel]) for channel in range(3)])
    return np.clip(result, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = ColorPaletteDialog(current_palette="Seismic")
    dialog.palette_selected.connect(lambda name: print(f"Selected: {name}"))
    dialog.exec()
    sys.exit(0)