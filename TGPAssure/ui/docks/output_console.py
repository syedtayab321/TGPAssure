from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QMenu,
    QPushButton, QTabBar, QToolButton, QVBoxLayout, QWidget, QPlainTextEdit, QSizePolicy
)

from ui.icons import get_icon, icon_color


class OutputConsole(QWidget):
    levels = ("INFO", "SUCCESS", "WARNING", "ERROR", "DEBUG")
    colours = {"INFO": "#0078D4", "SUCCESS": "#107C10", "WARNING": "#CA5010", "ERROR": "#D13438", "DEBUG": "#8A8A8A"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("outputConsole")
        self._entries: list[dict[str, str]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_container = QWidget(self)
        header_container.setObjectName("consoleHeader")
        header_container.setStyleSheet("")
        header = QHBoxLayout(header_container)
        header.setContentsMargins(6, 2, 6, 2)
        header.setSpacing(4)

        self.tabs = QTabBar(header_container)
        self.tabs.setObjectName("consoleTabs")
        self.tabs.setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        for label in ("Console", "QC Log", "Errors", "Warnings", "Info"):
            self.tabs.addTab(label)
        self.tabs.currentChanged.connect(self._rebuild_view)
        header.addWidget(self.tabs)
        header.addStretch(1)

        self.search = QLineEdit(header_container)
        self.search.setObjectName("consoleSearch")
        self.search.setPlaceholderText("Search")
        self.search.setFixedWidth(130)
        self.search.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.search.textChanged.connect(self._rebuild_view)
        self.search.setClearButtonEnabled(True)
        header.addWidget(self.search)

        def _tool_button(icon_name: str, tooltip: str, handler) -> QToolButton:
            button = QToolButton(header_container)
            button.setObjectName("consoleToolButton")
            icon = get_icon(icon_name, color="#4A5568", size=16)
            button.setIcon(icon)
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(26, 24)
            button.setToolTip(tooltip)
            button.setCursor(Qt.PointingHandCursor)
            button.setAutoRaise(True)
            button.clicked.connect(handler)
            return button

        self.copy_btn = _tool_button("edit-copy", "Copy console output", self.copy_all)
        header.addWidget(self.copy_btn)
        self.clear_btn = _tool_button("edit-clear", "Clear console", self.clear)
        header.addWidget(self.clear_btn)
        self.export_btn = _tool_button("document-export", "Export log to file", self.export)
        header.addWidget(self.export_btn)
        self.autoscroll = QCheckBox("Auto", header_container)
        self.autoscroll.setChecked(True)
        self.autoscroll.setToolTip("Auto-scroll to newest entries")
        header.addWidget(self.autoscroll)
        layout.addWidget(header_container)
        
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("consoleEditor")
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.editor, 1)
        self.search_shortcut = QKeySequence("Ctrl+F")

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Find):
            self.search.setFocus()
            self.search.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def log(self, level: str, message: str) -> None:
        entry = {"ts": datetime.now().strftime("%H:%M:%S"), "level": level.upper(), "msg": message}
        self._entries.append(entry)
        if self._matches(entry):
            self._append(entry)

    def _selected_level(self) -> str | None:
        return {2: "ERROR", 3: "WARNING", 4: "INFO"}.get(self.tabs.currentIndex())

    def _matches(self, entry: dict[str, str]) -> bool:
        level = self._selected_level()
        query = self.search.text().strip().lower()
        return (level is None or entry["level"] == level) and (not query or query in entry["msg"].lower() or query in entry["level"].lower())

    def _append(self, entry: dict[str, str]) -> None:
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.colours.get(entry["level"], "#1F1F1F")))
        cursor.insertText(f"[{entry['ts']}] [{entry['level']}] ", fmt)
        cursor.insertText(f"{entry['msg']}\n")
        if self.autoscroll.isChecked():
            self.editor.verticalScrollBar().setValue(self.editor.verticalScrollBar().maximum())

    def _rebuild_view(self, *_args) -> None:
        self.editor.clear()
        for entry in self._entries:
            if self._matches(entry):
                self._append(entry)

    def _show_context_menu(self, position) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #D1D9E0;
                border-radius: 4px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 5px 20px 5px 10px;
                color: #102A43;
            }
            QMenu::item:selected {
                background: #E5F1FB;
            }
        """)
        menu.addAction("Copy", self.editor.copy)
        menu.addAction("Select All", self.editor.selectAll)
        menu.addSeparator()
        menu.addAction("Clear", self.clear)
        menu.addAction("Export", self.export)
        menu.exec(self.editor.mapToGlobal(position))

    def clear(self) -> None:
        self._entries.clear()
        self.editor.clear()

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self.editor.toPlainText())

    def export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", str(Path.home()), "Text Files (*.txt)")
        if path:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")