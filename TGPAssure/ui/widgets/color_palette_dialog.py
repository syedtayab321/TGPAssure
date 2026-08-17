from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from core.visualization.palette_library import COLOR_PALETTES, DEFAULT_PALETTE, palette_rgb_array


_CUSTOM_PALETTE_FILE = Path.home() / ".tgpassure" / "custom_palettes.json"
_HEX_RE = re.compile(r"#?[0-9A-Fa-f]{6}")
_RGB_RE = re.compile(r"\b(\d{1,3})\s*[,;\s]\s*(\d{1,3})\s*[,;\s]\s*(\d{1,3})\b")


# ---------------------------------------------------------------------------
# Petrel-style colour table dialog tokens
# ---------------------------------------------------------------------------
BG = "#EFEFEF"
PANEL = "#FFFFFF"
BORDER = "#9DA5AF"
TEXT = "#111827"
MUTED = "#5F6975"
FOCUS = "#2C7FB8"
OK_GREEN = "#169B47"
CANCEL_RED = "#C62828"


def _load_custom_palettes() -> None:
    """Load user palettes into the shared runtime palette registry."""
    try:
        if not _CUSTOM_PALETTE_FILE.exists():
            return
        data = json.loads(_CUSTOM_PALETTE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        for name, colors in data.items():
            if not isinstance(name, str) or not isinstance(colors, list):
                continue
            clean = [str(c).upper() for c in colors if isinstance(c, str) and QColor(str(c)).isValid()]
            if len(clean) >= 2:
                COLOR_PALETTES[name] = clean
    except Exception:
        # A broken user palette file must never stop the application from opening.
        return


def _save_custom_palette(name: str, colors: list[str]) -> None:
    _CUSTOM_PALETTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, list[str]] = {}
    try:
        if _CUSTOM_PALETTE_FILE.exists():
            raw = json.loads(_CUSTOM_PALETTE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = {str(k): list(v) for k, v in raw.items() if isinstance(v, list)}
    except Exception:
        existing = {}
    existing[name] = colors
    _CUSTOM_PALETTE_FILE.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")


def _normalise_hex(value: str) -> str:
    value = value.strip().upper()
    return value if value.startswith("#") else f"#{value}"


def _parse_palette_file(path: str) -> list[str]:
    """Parse a simple custom palette file.

    Supported formats:
    - #RRGGBB values anywhere in TXT/CSV/PAL files
    - R,G,B / R G B triplets with 0-255 channel values
    """
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    colors: list[str] = []

    for match in _HEX_RE.findall(text):
        hex_color = _normalise_hex(match)
        if QColor(hex_color).isValid():
            colors.append(hex_color)

    if not colors:
        for r_text, g_text, b_text in _RGB_RE.findall(text):
            r, g, b = int(r_text), int(g_text), int(b_text)
            if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                colors.append(f"#{r:02X}{g:02X}{b:02X}")

    # Preserve order but remove duplicates created by mixed file formats.
    deduped: list[str] = []
    for color in colors:
        if color not in deduped:
            deduped.append(color)
    return deduped


def palette_icon(colors: list[str] | None = None, size: int = 22) -> QIcon:
    """Create a Petrel-like small color-table thumbnail."""
    colors = colors or COLOR_PALETTES.get("Seismic", ["#122452", "#DA3C2D"])
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    rect_x = 3
    rect_y = 2
    rect_w = max(14, size - 7)
    rect_h = max(16, size - 5)
    steps = max(8, min(24, rect_h))
    for row in range(steps):
        fraction = row / max(1, steps - 1)
        index = int(round(fraction * (len(colors) - 1))) if colors else 0
        painter.fillRect(rect_x, rect_y + row * rect_h // steps, rect_w, max(1, rect_h // steps + 1), QColor(colors[index]))

    painter.setPen(QColor("#202020"))
    painter.drawRect(rect_x, rect_y, rect_w, rect_h)
    painter.end()
    return QIcon(pixmap)


class ColorPaletteDialog(QDialog):
    """Petrel-style multi-column color table selector with custom palette import."""

    palette_selected = Signal(str)

    def __init__(self, current_palette: str = "Seismic", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        _load_custom_palettes()
        self.setWindowTitle("Select color table")
        self.setWindowIcon(palette_icon(COLOR_PALETTES.get(current_palette) or COLOR_PALETTES.get(DEFAULT_PALETTE)))
        self.setMinimumSize(720, 500)
        self.resize(1060, 760)
        self._selected_palette = current_palette if current_palette in COLOR_PALETTES else DEFAULT_PALETTE
        self._build_ui()
        self._populate()
        self._select_current_item()

    @property
    def selected_palette(self) -> str:
        return self._selected_palette

    def _build_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG};
                color: {TEXT};
                font-family: 'Segoe UI', Arial;
                font-size: 9.5pt;
            }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QComboBox, QLineEdit {{
                background: #FFFFFF;
                color: {TEXT};
                border: 1px solid #8E98A5;
                border-radius: 0px;
                min-height: 27px;
                padding: 2px 8px;
            }}
            QComboBox:focus, QLineEdit:focus {{ border: 1px solid {FOCUS}; }}
            QCheckBox {{ color: {MUTED}; spacing: 7px; }}
            QCheckBox::indicator {{ width: 19px; height: 19px; }}
            QPushButton {{
                background: #F5F5F5;
                border: 1px solid #A8B0BA;
                border-radius: 2px;
                min-height: 30px;
                padding: 4px 14px;
                color: {TEXT};
            }}
            QPushButton:hover {{ background: #E8F1FA; border-color: #7EA7CF; }}
            QPushButton:pressed {{ background: #D8E9F8; }}
            #addButton {{ min-width: 120px; }}
            #listFrame {{ background: {PANEL}; border: 1px solid {BORDER}; }}
            QListWidget {{
                background: #FFFFFF;
                border: none;
                outline: none;
                color: {TEXT};
                padding: 4px 3px 3px 3px;
            }}
            QListWidget::item {{
                height: 27px;
                padding: 1px 5px 1px 2px;
                margin: 0px;
            }}
            QListWidget::item:hover {{ background: #E8F2FF; }}
            QListWidget::item:selected {{
                background: #CFE7FF;
                color: #000000;
                border: 1px solid #5C9EDB;
            }}
            QScrollBar:horizontal, QScrollBar:vertical {{ background: #EFEFEF; border: 1px solid #C6C6C6; }}
            QScrollBar:horizontal {{ height: 19px; }}
            QScrollBar:vertical {{ width: 19px; }}
            QScrollBar::handle:horizontal, QScrollBar::handle:vertical {{ background: #D0D0D0; border: 1px solid #9A9A9A; }}
            QScrollBar::handle:horizontal:hover, QScrollBar::handle:vertical:hover {{ background: #BEBEBE; }}
            #okButton, #cancelButton {{
                min-width: 120px;
                min-height: 32px;
                font-size: 10pt;
            }}
            #okButton {{ color: #1B1B1B; }}
            #cancelButton {{ color: #1B1B1B; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        toolbar.addWidget(QLabel("View:"))

        self.view_combo = QComboBox(self)
        self.view_combo.addItem("List")
        self.view_combo.setFixedWidth(210)
        toolbar.addWidget(self.view_combo)

        self.group_check = QCheckBox("Group by folder", self)
        self.group_check.setEnabled(False)
        toolbar.addWidget(self.group_check)

        toolbar.addSpacing(18)
        toolbar.addWidget(QLabel("Name contains:"))
        self.search = QLineEdit(self)
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(230)
        self.search.textChanged.connect(self._populate)
        toolbar.addWidget(self.search)

        toolbar.addStretch(1)
        self.add_button = QPushButton("+ Add Custom", self)
        self.add_button.setObjectName("addButton")
        self.add_button.setToolTip("Import your own palette from TXT, CSV or PAL file")
        self.add_button.clicked.connect(self._add_custom_palette)
        toolbar.addWidget(self.add_button)
        root.addLayout(toolbar)

        list_frame = QFrame(self)
        list_frame.setObjectName("listFrame")
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self.list_widget = QListWidget(list_frame)
        self.list_widget.setIconSize(QSize(24, 24))
        self.list_widget.setViewMode(QListWidget.ViewMode.ListMode)
        self.list_widget.setFlow(QListWidget.Flow.TopToBottom)
        self.list_widget.setWrapping(True)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.list_widget.itemClicked.connect(self._item_clicked)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._accept())
        list_layout.addWidget(self.list_widget)
        root.addWidget(list_frame, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)
        footer.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.ok_button = QPushButton("✓ OK", self)
        self.ok_button.setObjectName("okButton")
        self.ok_button.clicked.connect(self._accept)
        footer.addWidget(self.ok_button)

        self.cancel_button = QPushButton("✕ Cancel", self)
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)

    def _display_name(self, name: str) -> str:
        return name if len(name) <= 22 else f"{name[:19]}..."

    def _populate(self, *_args) -> None:
        query = self.search.text().strip().lower()
        self.list_widget.clear()

        for name in sorted(COLOR_PALETTES.keys(), key=str.lower):
            if query and query not in name.lower():
                continue
            item = QListWidgetItem(palette_icon(COLOR_PALETTES[name], 23), self._display_name(name))
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(name)
            item.setSizeHint(QSize(166, 28))
            self.list_widget.addItem(item)

        self._select_current_item()

    def _select_current_item(self) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == self._selected_palette:
                self.list_widget.setCurrentItem(item)
                self.list_widget.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                return
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            item = self.list_widget.currentItem()
            if item is not None:
                self._selected_palette = item.data(Qt.ItemDataRole.UserRole)

    def _item_clicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        if name in COLOR_PALETTES:
            self._selected_palette = name

    def _add_custom_palette(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Add custom color table",
            "",
            "Color table files (*.txt *.csv *.pal *.lut *.clr);;All files (*.*)",
        )
        if not path:
            return

        try:
            colors = _parse_palette_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Add custom color table", f"Unable to read the selected file.\n\n{exc}")
            return

        if len(colors) < 2:
            QMessageBox.warning(
                self,
                "Add custom color table",
                "The selected file did not contain a valid color table.\n\n"
                "Use #RRGGBB colors or R,G,B values, one color per line.",
            )
            return

        default_name = Path(path).stem.strip() or "Custom palette"
        name, accepted = QInputDialog.getText(self, "Palette name", "Name:", text=default_name)
        if not accepted:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Palette name", "Please enter a valid palette name.")
            return

        if name in COLOR_PALETTES:
            reply = QMessageBox.question(
                self,
                "Replace color table",
                f"'{name}' already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        COLOR_PALETTES[name] = colors
        try:
            _save_custom_palette(name, colors)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Save custom color table",
                f"The palette was added for this session but could not be saved permanently.\n\n{exc}",
            )

        self._selected_palette = name
        self.search.clear()
        self._populate()
        QMessageBox.information(self, "Add custom color table", f"'{name}' has been added.")

    def _accept(self) -> None:
        item = self.list_widget.currentItem()
        if item is not None:
            name = item.data(Qt.ItemDataRole.UserRole)
            if name in COLOR_PALETTES:
                self._selected_palette = name
        self.palette_selected.emit(self._selected_palette)
        self.accept()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_and_center_on_screen()

    def _fit_and_center_on_screen(self) -> None:
        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else None
        if screen is None:
            screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        target_width = min(self.width(), int(available.width() * 0.92))
        target_height = min(self.height(), int(available.height() * 0.88))
        target_width = max(self.minimumWidth(), target_width)
        target_height = max(self.minimumHeight(), target_height)
        if self.width() != target_width or self.height() != target_height:
            self.resize(target_width, target_height)
        frame = self.frameGeometry()
        x = available.x() + (available.width() - frame.width()) // 2
        y = available.y() + (available.height() - frame.height()) // 2
        self.move(max(available.x(), x), max(available.y(), y))


def palette_to_rgb_array(name: str, samples: int = 256) -> np.ndarray:
    return palette_rgb_array(name, samples)


class PaletteSelectorButton(QPushButton):
    """Drop-in global palette selector button used by all modules."""

    currentTextChanged = Signal(str)

    def __init__(self, current_palette: str = DEFAULT_PALETTE, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        _load_custom_palettes()
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
