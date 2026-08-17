from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QGuiApplication, QIcon, QLinearGradient, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget,
)

from core.visualization.palette_library import COLOR_PALETTES, DEFAULT_PALETTE, palette_rgb_array


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
    return palette_rgb_array(name, samples)


class PaletteSelectorButton(QPushButton):
    """Drop-in palette selector with the TraceWaveform palette dialog everywhere."""

    currentTextChanged = Signal(str)

    def __init__(self, current_palette: str = DEFAULT_PALETTE, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._palette_name = current_palette if current_palette in COLOR_PALETTES else DEFAULT_PALETTE
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose_palette)
        self._refresh()

    def currentText(self) -> str:
        return self._palette_name

    def setCurrentText(self, name: str) -> None:
        name = name if name in COLOR_PALETTES else DEFAULT_PALETTE
        if name == self._palette_name:
            return
        self._palette_name = name
        self._refresh()
        self.currentTextChanged.emit(name)

    def _choose_palette(self) -> None:
        dialog = ColorPaletteDialog(self._palette_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.setCurrentText(dialog.selected_palette)

    def _refresh(self) -> None:
        self.setText(self._palette_name)
        self.setIcon(palette_icon(COLOR_PALETTES.get(self._palette_name)))
        self.setToolTip(f"Global color palette: {self._palette_name}. Click to change.")


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = ColorPaletteDialog(current_palette="Seismic")
    dialog.palette_selected.connect(lambda name: print(f"Selected: {name}"))
    dialog.exec()
    sys.exit(0)
