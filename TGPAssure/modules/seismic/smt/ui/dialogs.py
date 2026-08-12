from __future__ import annotations

import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.smt import (
    ImportOptions,
    MEASUREMENT_FIELDS,
    MEASUREMENT_LABELS,
    MeasurementLimit,
    SmtConfiguration,
    SmtProjectDatabase,
    SmtResultReader,
    default_project_directory,
)


# The palette intentionally follows the Windows-classic SMTAN2 screenshots in the
# supplied reference PDF.  Square controls, raised/sunken borders and grey panels
# are deliberate rather than inherited from the modern TGPAssure dashboard.
_CLASSIC_QSS = """
QDialog, QWidget#classicPage {
    background:#E7ECF1;
    color:#18232D;
    font-size:7.5pt;
}
QDialog QLabel, QWidget#classicPage QLabel,
QDialog QCheckBox, QWidget#classicPage QCheckBox,
QDialog QRadioButton, QWidget#classicPage QRadioButton {
    background:transparent;
    color:#18232D;
}
QGroupBox {
    border:1px solid #A6B4BF;
    border-radius:3px;
    margin-top:8px;
    padding-top:7px;
    background:#F1F5F8;
    color:#243746;
    font-weight:600;
}
QGroupBox::title {
    subcontrol-origin:margin;
    left:7px;
    padding:0 4px;
    background:#E7ECF1;
    color:#214E70;
}
QPushButton {
    min-height:22px;
    padding:2px 7px;
    border:1px solid #A7B5C0;
    border-radius:3px;
    background:#F3F6F8;
    color:#172530;
}
QPushButton:hover { background:#E2F0FA; border-color:#5897BE; }
QPushButton:pressed { background:#CEE3F1; border-color:#397EA8; }
QPushButton:disabled { background:#E2E7EB; color:#7B8790; border-color:#C3CCD3; }
QPushButton#largeClassic {
    min-height:38px;
    font-weight:700;
    text-align:left;
    padding-left:8px;
    background:#EDF3F7;
}
QPushButton#largeClassic:hover { background:#DCECF7; }
QPushButton#primaryClassic {
    font-weight:700;
    background:#DCECF7;
    border-color:#6E9DBB;
    color:#123F68;
}
QLineEdit, QComboBox, QDateEdit, QSpinBox {
    min-height:19px;
    border:1px solid #8EA3B2;
    border-radius:2px;
    background:#FFFFFF;
    color:#172530;
    selection-background-color:#2D83B5;
    selection-color:#FFFFFF;
    padding:1px 3px;
}
QLineEdit:read-only { background:#EEF2F5; color:#465762; }
QComboBox QAbstractItemView {
    background:#FFFFFF;
    color:#172530;
    selection-background-color:#D6EAF7;
    selection-color:#172530;
    border:1px solid #8EA3B2;
}
QListWidget, QTableWidget, QPlainTextEdit {
    border:1px solid #8EA3B2;
    border-radius:2px;
    background:#FFFFFF;
    color:#172530;
    alternate-background-color:#EEF4F7;
    gridline-color:#C2CDD5;
    selection-background-color:#D4EAF7;
    selection-color:#172530;
}
QHeaderView::section {
    background:#D8E4EC;
    color:#203744;
    border:0;
    border-right:1px solid #AAB8C2;
    border-bottom:1px solid #9EAFBB;
    padding:3px;
    font-weight:650;
}
QScrollBar:vertical, QScrollBar:horizontal { background:#E1E7EC; border:0; }
QProgressBar {
    border:1px solid #8EA3B2;
    border-radius:2px;
    background:#FFFFFF;
    color:#172530;
    text-align:center;
}
QProgressBar::chunk { background:#2B9961; }
QFrame#classicTitleBar {
    min-height:23px;
    max-height:23px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #163D69, stop:0.58 #28729B, stop:1 #60A8C8);
    border:1px solid #123555;
}
QLabel#classicTitleText {
    background:transparent;
    color:#FFFFFF;
    font-weight:700;
    font-size:8pt;
}
QLabel#blueProject {
    background:#DDECF8;
    color:#123F68;
    border:1px solid #8DB3CF;
    border-radius:3px;
    padding:3px 6px;
    font-size:11pt;
    font-weight:700;
}
QLabel#readyLabel {
    background:#EAF5E8;
    color:#3F772F;
    border:1px solid #A9C9A2;
    border-radius:3px;
    padding:2px 6px;
    font-size:11pt;
    font-weight:700;
}
QLabel#countLabel {
    background:transparent;
    color:#376C2F;
    font-size:20pt;
    font-weight:700;
}
QLabel#smallBlue { background:transparent; color:#164C76; }
QToolTip {
    background:#FFFBE6;
    color:#16212A;
    border:1px solid #9A8F56;
    padding:3px;
}
"""


def _set_classic(widget: QWidget) -> None:
    widget.setStyleSheet(_CLASSIC_QSS)



def _center_on_parent_or_screen(dialog: QDialog) -> None:
    parent = dialog.parentWidget()
    if parent is not None and parent.isVisible():
        target = parent.frameGeometry().center()
        available = parent.screen().availableGeometry() if parent.screen() else QApplication.primaryScreen().availableGeometry()
    else:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else dialog.frameGeometry()
        target = available.center()
    frame = dialog.frameGeometry()
    frame.moveCenter(target)
    if frame.left() < available.left():
        frame.moveLeft(available.left() + 8)
    if frame.top() < available.top():
        frame.moveTop(available.top() + 8)
    if frame.right() > available.right():
        frame.moveRight(available.right() - 8)
    if frame.bottom() > available.bottom():
        frame.moveBottom(available.bottom() - 8)
    dialog.move(frame.topLeft())


def _fit_dialog_to_screen(dialog: QDialog, preferred_width: int, preferred_height: int, min_width: int = 760, min_height: int = 520) -> None:
    screen = dialog.parentWidget().screen() if dialog.parentWidget() is not None and dialog.parentWidget().screen() else QApplication.primaryScreen()
    available = screen.availableGeometry() if screen else dialog.frameGeometry()
    width = max(min_width, min(preferred_width, available.width() - 56))
    height = max(min_height, min(preferred_height, available.height() - 72))
    dialog.resize(width, height)


_RESULTS_QSS = _CLASSIC_QSS + """
QDialog#smtResultsDialog {
    background:#F2F5F8;
    font-size:7pt;
}
QDialog#smtResultsDialog QWidget#classicPage {
    background:#FFFFFF;
    border:1px solid #D3DCE6;
    border-radius:6px;
}
QDialog#smtResultsDialog QGroupBox {
    background:#FFFFFF;
    border:1px solid #CDD8E3;
    border-radius:6px;
    margin-top:8px;
    padding-top:8px;
}
QDialog#smtResultsDialog QPushButton {
    min-height:22px;
    border-radius:5px;
    font-weight:700;
}
QDialog#smtResultsDialog QPushButton#primaryClassic {
    background:#DCECF7;
    color:#123F68;
    border-color:#6E9DBB;
}
QDialog#smtResultsDialog QTableWidget {
    font-size:7pt;
}
QDialog#smtResultsDialog QPlainTextEdit {
    font-size:7pt;
}
"""

def _icon(widget: QWidget, pixmap: QStyle.StandardPixmap):
    return widget.style().standardIcon(pixmap)


def _classic_title(text: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("classicTitleBar")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(7, 3, 7, 3)
    label = QLabel(text)
    label.setObjectName("classicTitleText")
    layout.addWidget(label)
    layout.addStretch(1)
    return frame


def _prep_table(table: QTableWidget, *, editable: bool = False, checkbox_rows: bool = False) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    if not editable:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(True)
    if checkbox_rows:
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)


def _date_edit(value: date | None = None) -> QDateEdit:
    current = value or date.today()
    widget = QDateEdit(QDate(current.year, current.month, current.day))
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("dd-MMM-yyyy")
    return widget


def _qdate_to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _export_plot_png(plot: pg.PlotWidget, parent: QWidget, suggested: str) -> None:
    path, _ = QFileDialog.getSaveFileName(parent, "Export PNG", suggested, "PNG image (*.png)")
    if not path:
        return
    if not path.lower().endswith(".png"):
        path += ".png"
    try:
        from pyqtgraph.exporters import ImageExporter

        exporter = ImageExporter(plot.plotItem)
        exporter.parameters()["width"] = max(1400, plot.width() * 2)
        exporter.export(path)
        QMessageBox.information(parent, "SMTAN2", f"PNG exported:\n{path}")
    except Exception as exc:
        QMessageBox.critical(parent, "SMTAN2", f"Unable to export PNG:\n{exc}")


def _print_widget(widget: QWidget, parent: QWidget) -> None:
    try:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        pixmap = widget.grab()
        painter = QPainter(printer)
        target = painter.viewport()
        scaled = pixmap.size()
        scaled.scale(target.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter.setViewport(target.x(), target.y(), scaled.width(), scaled.height())
        painter.setWindow(pixmap.rect())
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
    except Exception as exc:
        QMessageBox.critical(parent, "SMTAN2", f"Unable to print:\n{exc}")


def _format_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.7g}"
    return str(value)


def _statistics_text(database: SmtProjectDatabase, stats: dict[str, Any]) -> str:
    lines = [
        "-" * 78,
        f"Statistics for {database.project_name}",
        "-" * 78,
        f"Total records in specified range          = {stats['total_records']:,}",
        f"Total failures found by program           = {stats['total_failures']:,}",
        f"Total failures reported by SMT            = {stats['source_failures']:,}",
        f"Total SMT OK, but Program Flags Bad       = {stats['source_good_program_fail']:,}",
        "",
        f"Unique Strings Tested                     = {stats['total_unique_strings']:,}",
    ]
    for count, strings in sorted(stats["test_frequency"].items(), key=lambda item: int(item[0])):
        lines.append(f"Number of Strings Tested {int(count):>3} Times         = {int(strings):,}")
    lines.extend(["", "Statistical Analysis of GOOD strings", ""])
    lines.append(
        f"{'':<14}{'Average':>11}{'St. Dev.':>11}{'Skewness':>11}{'Kurtosis':>11}{'Maximum':>11}{'Minimum':>11}"
    )
    for field_name in MEASUREMENT_FIELDS:
        data = stats["numeric_good"][field_name]
        if not data["count"]:
            lines.append(f"{MEASUREMENT_LABELS[field_name]:<14}{'--':>11}")
            continue
        lines.append(
            f"{MEASUREMENT_LABELS[field_name]:<14}{data['average']:>11.5g}{data['std_dev']:>11.5g}"
            f"{data['skewness']:>11.5g}{data['kurtosis']:>11.5g}{data['maximum']:>11.5g}{data['minimum']:>11.5g}"
        )
    lines.extend(["", "Failure Breakdown", ""])
    for name, count in sorted(stats["failure_counts"].items(), key=lambda item: int(item[1]), reverse=True):
        lines.append(f"{MEASUREMENT_LABELS.get(name, name.replace('_', ' ').title()):<32} = {int(count):,}")
    return "\n".join(lines)


class ProjectSelectionDialog(QDialog):
    """Classic SMTAN2 New/Select Project screen."""

    def __init__(self, parent: QWidget | None = None, directory: str | Path | None = None, current_path: str | Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Or Select Project")
        self.resize(560, 360)
        _set_classic(self)
        self.directory = Path(directory) if directory else default_project_directory()
        self.selected_path: Path | None = None
        self.current_path = Path(current_path).resolve() if current_path else None

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.addWidget(_classic_title("New Or Select Project"))

        body = QVBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter a new SMT project name")
        body.addWidget(self.name_edit)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda *_: self._select())
        body.addWidget(self.list_widget, 1)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Project Folder"))
        self.folder_edit = QLineEdit(str(self.directory))
        folder_row.addWidget(self.folder_edit, 1)
        browse = QPushButton("Browse")
        browse.setIcon(_icon(self, QStyle.StandardPixmap.SP_DirOpenIcon))
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse)
        body.addLayout(folder_row)
        root.addLayout(body, 1)

        buttons = QHBoxLayout()
        ok = QPushButton("OK")
        ok.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogApplyButton))
        ok.clicked.connect(self._ok)
        clear = QPushButton("Clear")
        clear.setIcon(_icon(self, QStyle.StandardPixmap.SP_DriveFDIcon))
        clear.clicked.connect(self.name_edit.clear)
        delete = QPushButton("Delete")
        delete.setIcon(_icon(self, QStyle.StandardPixmap.SP_TrashIcon))
        delete.clicked.connect(self._delete)
        cancel = QPushButton("Cancel")
        cancel.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogCancelButton))
        cancel.clicked.connect(self.reject)
        for button in (ok, clear, delete, cancel):
            button.setMinimumHeight(36)
            buttons.addWidget(button)
        root.addLayout(buttons)

        self.status = QLineEdit()
        self.status.setReadOnly(True)
        root.addWidget(self.status)
        self._refresh()

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "SMT Project Folder", self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)
            self._refresh()

    def _refresh(self) -> None:
        self.directory = Path(self.folder_edit.text()).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.list_widget.clear()
        for path in SmtProjectDatabase.list_projects(self.directory):
            item = QListWidgetItem(path.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            if self.current_path is not None and path.resolve() == self.current_path:
                item.setToolTip("Currently open project")
            self.list_widget.addItem(item)
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)
        self.status.setText(f"{self.list_widget.count()} SMT project database(s). Select a project explicitly or type a new name.")

    def _ok(self) -> None:
        name = self.name_edit.text().strip()
        if name:
            try:
                database = SmtProjectDatabase.create(self.directory, name)
                self.selected_path = database.path
                database.close()
                QMessageBox.information(
                    self,
                    "SMTAN2",
                    f"{self.selected_path} Created, you may now add data",
                )
                self.accept()
                return
            except FileExistsError:
                QMessageBox.warning(self, "SMTAN2", "A project with that name already exists.")
                return
            except Exception as exc:
                QMessageBox.critical(self, "SMTAN2", f"Unable to create project:\n{exc}")
                return
        self._select()

    def _select(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "SMTAN2", "Enter a new project name or select an existing project.")
            return
        self.selected_path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        self.accept()

    def _delete(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        answer = QMessageBox.question(
            self,
            "Delete SMT Project",
            f"Permanently delete '{path.stem}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink(missing_ok=True)
            Path(str(path) + "-wal").unlink(missing_ok=True)
            Path(str(path) + "-shm").unlink(missing_ok=True)
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", f"Unable to delete project:\n{exc}")


class ImportRecordsDialog(QDialog):
    """SMT file loader matching the PDF's Load SMT Files dialog."""

    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.summary = None
        self.setWindowTitle("Load SMT Files")
        self.resize(620, 500)
        _set_classic(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.addWidget(_classic_title("Load SMT Files"))

        select = QPushButton("Select and Load SMT Files")
        select.setObjectName("largeClassic")
        select.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogOpenButton))
        select.clicked.connect(self._select_and_load)
        root.addWidget(select)

        summary_grid = QGridLayout()
        labels = ["Records Added", "Files Processed", "Duplicate Files", "Test Failures"]
        self.summary_labels: dict[str, QLabel] = {}
        for row, label in enumerate(labels):
            summary_grid.addWidget(QLabel(label), row, 0)
            value = QLabel("0")
            value.setFrameShape(QFrame.Shape.Panel)
            value.setFrameShadow(QFrame.Shadow.Sunken)
            value.setMinimumWidth(100)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            summary_grid.addWidget(value, row, 1)
            self.summary_labels[label] = value
        summary_grid.setColumnStretch(2, 1)

        pending = QGroupBox("Update Pending Test Table")
        p_layout = QVBoxLayout(pending)
        self.pending_group = QButtonGroup(self)
        for label, key in (
            ("Manual (Utilities -> Pending)", "manual"),
            ("After Each File Loaded", "after_each"),
            ("After All Files Loaded", "after_all"),
        ):
            radio = QRadioButton(label)
            radio.setProperty("value", key)
            self.pending_group.addButton(radio)
            p_layout.addWidget(radio)
        self.pending_group.buttons()[0].setChecked(True)
        summary_grid.addWidget(pending, 0, 3, 4, 1)
        root.addLayout(summary_grid)

        invalid = QGroupBox("Action on Invalid Date in Header")
        grid = QGridLayout(invalid)
        self.bad_date_group = QButtonGroup(self)
        for row, (label, key) in enumerate((("Warn", "warn"), ("Accept", "accept"), ("Reject", "reject"), ("Correct", "correct"))):
            radio = QRadioButton(label)
            radio.setProperty("value", key)
            self.bad_date_group.addButton(radio)
            grid.addWidget(radio, row, 0)
        self.bad_date_group.buttons()[0].setChecked(True)
        self.replacement_group = QButtonGroup(self)
        for row, (label, key) in enumerate((("Use Today's Date", "today"), ("Use Yesterday's Date", "yesterday"), ("Use File's Date", "file"))):
            radio = QRadioButton(label)
            radio.setProperty("value", key)
            self.replacement_group.addButton(radio)
            grid.addWidget(radio, row, 2)
        self.replacement_group.buttons()[2].setChecked(True)
        grid.addWidget(QLabel("Minimum Valid Year"), 4, 0)
        self.minimum_year = QSpinBox()
        self.minimum_year.setRange(1900, 2200)
        self.minimum_year.setValue(database.load_configuration().minimum_valid_year)
        grid.addWidget(self.minimum_year, 4, 1)
        grid.addWidget(QLabel("Duplicate rows"), 4, 2)
        self.duplicates = QComboBox()
        self.duplicates.addItem("Skip", "skip")
        self.duplicates.addItem("Replace", "replace")
        self.duplicates.addItem("Allow", "allow")
        grid.addWidget(self.duplicates, 4, 3)
        root.addWidget(invalid)

        last_row = QHBoxLayout()
        last = QLabel("Last File")
        last.setObjectName("smallBlue")
        last_row.addWidget(last)
        self.last_file = QLineEdit()
        self.last_file.setReadOnly(True)
        last_row.addWidget(self.last_file, 1)
        root.addLayout(last_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)
        self.ready = QLabel("Ready")
        self.ready.setObjectName("readyLabel")
        self.ready.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.ready)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(88)
        root.addWidget(self.details)

        cancel = QPushButton("Cancel")
        cancel.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogCancelButton))
        cancel.clicked.connect(self.reject)
        root.addWidget(cancel)

    @staticmethod
    def _selected_value(group: QButtonGroup, default: str) -> str:
        button = group.checkedButton()
        return str(button.property("value")) if button is not None else default

    def _select_and_load(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select and Load SMT Files",
            str(Path.home()),
            "SMT/Text Results (*.csv *.txt *.tsv *.dat *.asc *.smt *.log *.out);;All files (*.*)",
        )
        if not paths:
            return
        options = ImportOptions(
            minimum_valid_year=self.minimum_year.value(),
            bad_date_mode=self._selected_value(self.bad_date_group, "warn"),
            replacement_date=self._selected_value(self.replacement_group, "file"),
            duplicate_mode=str(self.duplicates.currentData()),
            update_pending=self._selected_value(self.pending_group, "manual"),
        )
        reader = SmtResultReader()
        records = []
        warnings: list[str] = []
        self.details.clear()
        self.ready.setText("Loading...")
        QApplication.processEvents()
        try:
            for index, raw_path in enumerate(paths, start=1):
                path = Path(raw_path)
                self.last_file.setText(str(path))
                self.details.appendPlainText(f"Reading {path.name}")
                parsed, file_warnings = reader.read(path, options)
                records.extend(parsed)
                warnings.extend(file_warnings)
                self.progress.setValue(int(index / len(paths) * 55))
                QApplication.processEvents()
            summary = self.database.add_records(records, options)
            summary.files = len(paths)
            summary.warnings.extend(warnings)
            self.summary = summary
            self.progress.setValue(100)
            failures = sum(1 for row in records if str(row.source_result).upper() in {"FAIL", "FAILED", "BAD", "NG"})
            self.summary_labels["Records Added"].setText(f"{summary.inserted:,}")
            self.summary_labels["Files Processed"].setText(f"{len(paths):,}")
            self.summary_labels["Duplicate Files"].setText(f"{summary.duplicates:,}")
            self.summary_labels["Test Failures"].setText(f"{failures:,}")
            self.ready.setText("Ready")
            self.details.appendPlainText(
                f"Inserted {summary.inserted:,}; replaced {summary.replaced:,}; duplicates {summary.duplicates:,}; "
                f"corrected dates {summary.corrected_dates:,}."
            )
            for warning in warnings[:40]:
                self.details.appendPlainText("Warning: " + warning)
            QMessageBox.information(self, "SMTAN2", f"{summary.inserted:,} SMT records loaded successfully.")
            self.accept()
        except Exception as exc:
            self.progress.setValue(0)
            self.ready.setText("Error")
            self.details.appendPlainText(str(exc))
            QMessageBox.critical(self, "SMTAN2", f"Unable to load SMT files:\n{exc}")


class ConfigurationDialog(QDialog):
    """Classic Test Limits and Parameters screen from the PDF."""

    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.configuration = database.load_configuration()
        self.limit_edits: dict[str, dict[str, QLineEdit]] = {}
        self.color_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle("Test Limits and Parameters")
        self.resize(920, 560)
        _set_classic(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.addWidget(_classic_title("Test Limits and Parameters"))
        body = QHBoxLayout()
        left = QVBoxLayout()

        limits = QGroupBox("SMT Limits")
        grid = QGridLayout(limits)
        grid.addWidget(QLabel(""), 0, 0)
        for col, field_name in enumerate(MEASUREMENT_FIELDS, start=1):
            header = QLabel(MEASUREMENT_LABELS[field_name])
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(header, 0, col)
            self.limit_edits[field_name] = {}
        for row, key in enumerate(("maximum", "nominal", "minimum"), start=1):
            grid.addWidget(QLabel({"maximum": "Max", "nominal": "Nom", "minimum": "Min"}[key]), row, 0)
            for col, field_name in enumerate(MEASUREMENT_FIELDS, start=1):
                value = getattr(self.configuration.limits[field_name], key)
                edit = QLineEdit("" if value is None else f"{value:g}")
                edit.setMaximumWidth(82)
                edit.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.limit_edits[field_name][key] = edit
                grid.addWidget(edit, row, col)
        grid.addWidget(QLabel("Colours"), 4, 0)
        for col, field_name in enumerate(MEASUREMENT_FIELDS, start=1):
            color = self.configuration.limits[field_name].color
            button = QPushButton("")
            button.setMinimumHeight(23)
            button.setStyleSheet(f"background:{color}; border:2px outset #F2F2F2;")
            button.setProperty("color", color)
            button.clicked.connect(lambda _checked=False, key=field_name: self._choose_color(key))
            self.color_buttons[field_name] = button
            grid.addWidget(button, 4, col)
        grid.addWidget(QLabel("Reference String 1"), 5, 0)
        self.reference_1 = QLineEdit(self.configuration.reference_string_1)
        grid.addWidget(self.reference_1, 5, 1, 1, 2)
        grid.addWidget(QLabel("Reference String 2"), 6, 0)
        self.reference_2 = QLineEdit(self.configuration.reference_string_2)
        grid.addWidget(self.reference_2, 6, 1, 1, 2)
        defaults = QPushButton("Defaults")
        defaults.clicked.connect(self._defaults)
        grid.addWidget(defaults, 5, 3, 2, 2)
        from_file = QPushButton("Get From SMT File")
        from_file.clicked.connect(self._get_from_smt_file)
        grid.addWidget(from_file, 5, 5, 2, 4)
        left.addWidget(limits)

        details = QGridLayout()
        self.contractor = QLineEdit(self.configuration.contractor)
        self.crew = QLineEdit(self.configuration.crew)
        self.client = QLineEdit(self.configuration.client)
        self.description = QLineEdit(self.configuration.string_description)
        self.string_min = QSpinBox(); self.string_min.setRange(0, 99999999); self.string_min.setValue(self.configuration.string_min)
        self.string_max = QSpinBox(); self.string_max.setRange(0, 99999999); self.string_max.setValue(self.configuration.string_max)
        self.histogram = QSpinBox(); self.histogram.setRange(5, 200); self.histogram.setValue(self.configuration.histogram_bins)
        self.min_year = QSpinBox(); self.min_year.setRange(1900, 2200); self.min_year.setValue(self.configuration.minimum_valid_year)
        rows = [
            ("Contractor", self.contractor), ("Crew", self.crew), ("Client", self.client),
            ("String Description", self.description), ("String ID Min", self.string_min),
            ("String ID Max", self.string_max), ("Histogram Bars (20-30)", self.histogram),
            ("Minimum valid Year", self.min_year),
        ]
        for row, (label, widget) in enumerate(rows):
            details.addWidget(QLabel(label), row, 0)
            details.addWidget(widget, row, 1)
        self.logo_path = QLineEdit(self.configuration.logo_path)
        logo_browse = QPushButton("Logo")
        logo_browse.clicked.connect(self._browse_logo)
        details.addWidget(logo_browse, 0, 3)
        details.addWidget(self.logo_path, 1, 3, 2, 1)
        self.show_logo = QCheckBox("Show Logo")
        self.show_logo.setChecked(self.configuration.show_logo)
        details.addWidget(self.show_logo, 3, 3)
        self.sgt = QCheckBox("Sercel SGT Support")
        self.sgt.setChecked(self.configuration.special_sgt_support)
        details.addWidget(self.sgt, 0, 4)
        left.addLayout(details)
        left.addStretch(1)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        load = QPushButton("Load")
        load.setIcon(_icon(self, QStyle.StandardPixmap.SP_DirOpenIcon))
        load.clicked.connect(self._load_json)
        save = QPushButton("Save")
        save.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogSaveButton))
        save.clicked.connect(self._save_json)
        maintenance = QPushButton("DB Maintenance")
        maintenance.setIcon(_icon(self, QStyle.StandardPixmap.SP_ComputerIcon))
        maintenance.clicked.connect(self._maintenance)
        ok = QPushButton("OK")
        ok.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogApplyButton))
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogCancelButton))
        cancel.clicked.connect(self.reject)
        for button in (load, save, maintenance, ok, cancel):
            button.setMinimumSize(155, 50)
            button.setStyleSheet(button.styleSheet() + "font-weight:700;")
            right.addWidget(button)
        right.addStretch(1)
        body.addLayout(right)
        root.addLayout(body, 1)

    @staticmethod
    def _value(edit: QLineEdit) -> float | None:
        text = edit.text().strip()
        if not text:
            return None
        return float(text)

    def _build_configuration(self) -> SmtConfiguration:
        limits: dict[str, MeasurementLimit] = {}
        for field_name in MEASUREMENT_FIELDS:
            controls = self.limit_edits[field_name]
            limits[field_name] = MeasurementLimit(
                minimum=self._value(controls["minimum"]),
                nominal=self._value(controls["nominal"]),
                maximum=self._value(controls["maximum"]),
                color=str(self.color_buttons[field_name].property("color") or "#00FF00"),
            )
            if limits[field_name].minimum is not None and limits[field_name].maximum is not None:
                if limits[field_name].minimum > limits[field_name].maximum:
                    raise ValueError(f"{MEASUREMENT_LABELS[field_name]} minimum is greater than maximum.")
        return SmtConfiguration(
            contractor=self.contractor.text().strip(),
            client=self.client.text().strip(),
            crew=self.crew.text().strip(),
            string_description=self.description.text().strip(),
            string_min=self.string_min.value(),
            string_max=self.string_max.value(),
            histogram_bins=self.histogram.value(),
            minimum_valid_year=self.min_year.value(),
            reference_string_1=self.reference_1.text().strip(),
            reference_string_2=self.reference_2.text().strip(),
            logo_path=self.logo_path.text().strip(),
            show_logo=self.show_logo.isChecked(),
            special_sgt_support=self.sgt.isChecked(),
            supported_models=("SMT200", "SMT300", "SMT400", "SGT-II") if self.sgt.isChecked() else ("SMT200", "SMT300", "SMT400"),
            polarity_fail_words=self.configuration.polarity_fail_words,
            limits=limits,
        )

    def _accept(self) -> None:
        try:
            configuration = self._build_configuration()
            self.database.save_configuration(configuration)
            self.configuration = configuration
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", f"Unable to save configuration:\n{exc}")

    def _apply(self, config: SmtConfiguration) -> None:
        self.configuration = config
        for field_name in MEASUREMENT_FIELDS:
            limit = config.limits[field_name]
            for key in ("minimum", "nominal", "maximum"):
                value = getattr(limit, key)
                self.limit_edits[field_name][key].setText("" if value is None else f"{value:g}")
            self.color_buttons[field_name].setProperty("color", limit.color)
            self.color_buttons[field_name].setStyleSheet(f"background:{limit.color}; border:2px outset #F2F2F2;")
        self.reference_1.setText(config.reference_string_1)
        self.reference_2.setText(config.reference_string_2)
        self.contractor.setText(config.contractor)
        self.client.setText(config.client)
        self.crew.setText(config.crew)
        self.description.setText(config.string_description)
        self.string_min.setValue(config.string_min)
        self.string_max.setValue(config.string_max)
        self.histogram.setValue(config.histogram_bins)
        self.min_year.setValue(config.minimum_valid_year)
        self.logo_path.setText(config.logo_path)
        self.show_logo.setChecked(config.show_logo)
        self.sgt.setChecked(config.special_sgt_support)

    def _defaults(self) -> None:
        self._apply(SmtConfiguration.defaults())

    def _choose_color(self, field_name: str) -> None:
        current = QColor(str(self.color_buttons[field_name].property("color") or "#00FF00"))
        color = QColorDialog.getColor(current, self, f"{MEASUREMENT_LABELS[field_name]} Colour")
        if color.isValid():
            value = color.name().upper()
            self.color_buttons[field_name].setProperty("color", value)
            self.color_buttons[field_name].setStyleSheet(f"background:{value}; border:2px outset #F2F2F2;")

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Logo", self.logo_path.text(), "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.logo_path.setText(path)

    def _load_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load SMT Configuration", str(self.database.path.parent), "JSON (*.json)")
        if not path:
            return
        try:
            self._apply(SmtConfiguration.from_dict(json.loads(Path(path).read_text(encoding="utf-8"))))
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", f"Unable to load configuration:\n{exc}")

    def _save_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save SMT Configuration", str(self.database.path.with_suffix(".configuration.json")), "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            Path(path).write_text(json.dumps(self._build_configuration().to_dict(), indent=2), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", f"Unable to save configuration:\n{exc}")

    def _get_from_smt_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Get Limits From SMT File", str(Path.home()), "SMT/Text/JSON (*.smt *.txt *.csv *.dat *.json);;All files (*.*)"
        )
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8", errors="replace")
            if Path(path).suffix.lower() == ".json":
                config = SmtConfiguration.from_dict(json.loads(raw))
                self._apply(config)
                return
            found = 0
            for field_name in MEASUREMENT_FIELDS:
                label = re.escape(MEASUREMENT_LABELS[field_name])
                for key, aliases in {
                    "minimum": ("min", "minimum"),
                    "nominal": ("nom", "nominal", "target"),
                    "maximum": ("max", "maximum"),
                }.items():
                    alias = "|".join(aliases)
                    match = re.search(rf"(?im)\b{label}\b[^\r\n]*?\b(?:{alias})\b\s*[:=,]\s*(-?\d+(?:\.\d+)?)", raw)
                    if match:
                        self.limit_edits[field_name][key].setText(match.group(1))
                        found += 1
            if not found:
                QMessageBox.information(
                    self,
                    "SMTAN2",
                    "No textual Min/Nom/Max limit declarations were found. The proprietary binary limit block is not documented in the PDF.",
                )
            else:
                QMessageBox.information(self, "SMTAN2", f"Loaded {found} limit value(s) from the SMT text file.")
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", f"Unable to read limits:\n{exc}")

    def _maintenance(self) -> None:
        MaintenanceDialog(self.database, self).exec()


class RecordsDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.rows: list[dict[str, Any]] = []
        self.setWindowTitle("SMT Database Records")
        self.resize(1050, 620)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("SMT Database Records"))
        controls = QHBoxLayout()
        self.all_dates = QCheckBox("All")
        self.all_dates.setChecked(True)
        self.start = _date_edit(date.today() - timedelta(days=30))
        self.end = _date_edit(date.today())
        self.status = QComboBox(); self.status.addItems(["All", "PASS", "WARN", "FAIL"])
        self.tester = QComboBox(); self.tester.addItem("All testers", "")
        self.model = QComboBox(); self.model.addItem("All models", "")
        self.string = QLineEdit(); self.string.setPlaceholderText("Exact string/serial")
        for value in database.distinct_values("tester"):
            self.tester.addItem(value, value)
        for value in database.distinct_values("model"):
            self.model.addItem(value, value)
        go = QPushButton("Go"); go.clicked.connect(self.refresh)
        export = QPushButton("Export CSV"); export.clicked.connect(self._export)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        controls.addWidget(self.all_dates); controls.addWidget(QLabel("From")); controls.addWidget(self.start)
        controls.addWidget(QLabel("To")); controls.addWidget(self.end); controls.addWidget(QLabel("Result")); controls.addWidget(self.status)
        controls.addWidget(QLabel("Tester")); controls.addWidget(self.tester); controls.addWidget(QLabel("Model")); controls.addWidget(self.model)
        controls.addWidget(QLabel("String")); controls.addWidget(self.string); controls.addWidget(go); controls.addWidget(export); controls.addWidget(close)
        root.addLayout(controls)
        self.table = QTableWidget(0, 21)
        self.table.setHorizontalHeaderLabels([
            "Status", "String", "Serial", "Test Date", "Tester", "Operator", "Model", "Noise", "Resistance", "Frequency",
            "Damping", "Sensitivity", "Temperature", "Distortion", "Impedance", "Polarity", "Source Result", "Failure Flags",
            "Source File", "Row", "Notes",
        ])
        _prep_table(self.table)
        root.addWidget(self.table, 1)
        self.summary = QLabel()
        root.addWidget(self.summary)
        self.refresh()

    def refresh(self) -> None:
        start = None if self.all_dates.isChecked() else _qdate_to_date(self.start.date())
        end = None if self.all_dates.isChecked() else _qdate_to_date(self.end.date())
        self.rows = self.database.query_records(
            start=start, end=end, result=self.status.currentText(), tester=str(self.tester.currentData() or ""),
            model=str(self.model.currentData() or ""), string_no=self.string.text().strip(), limit=100000,
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for data in self.rows:
            row = self.table.rowCount(); self.table.insertRow(row)
            values = [
                data["status"], data["string_no"], data["serial"], data["tested_at"], data["tester"], data["operator"], data["model"],
                data["noise"], data["resistance"], data["frequency"], data["damping"], data["sensitivity"], data["temperature"],
                data["distortion"], data["impedance"], data["polarity"], data["source_result"], ", ".join(data.get("failure_flags", [])),
                data["source_file"], data["source_row"], data["notes"],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(_format_number(value))
                if col == 0:
                    status = str(value)
                    item.setBackground(QColor({"PASS": "#C8FFC8", "WARN": "#FFF0A8", "FAIL": "#FFC8C8"}.get(status, "#FFFFFF")))
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.summary.setText(f"Showing {len(self.rows):,} record(s) of {self.database.record_count():,}")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export SMT Records", str(self.database.path.with_name(self.database.path.stem + "_records.csv")), "CSV (*.csv)")
        if path:
            try:
                self.database.export_records_csv(path, self.rows or None)
            except Exception as exc:
                QMessageBox.critical(self, "SMTAN2", str(exc))


class ResultsDialog(QDialog):
    """Histogram, scatter, cross-plot, numerics and statistics in the PDF layout."""

    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.config = database.load_configuration()
        self.rows: list[dict[str, Any]] = []
        self.setWindowTitle("SMT Results")
        self.setObjectName("smtResultsDialog")
        _fit_dialog_to_screen(self, 1180, 720)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(_RESULTS_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(_classic_title("Results"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(5)

        top_buttons = QGridLayout()
        print_button = QPushButton("Print")
        print_button.setIcon(_icon(self, QStyle.StandardPixmap.SP_FileDialogDetailedView))
        print_button.clicked.connect(lambda: _print_widget(self.output_stack.currentWidget(), self))
        png = QPushButton("PNG")
        png.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogSaveButton))
        png.clicked.connect(self._export_current_png)
        close = QPushButton("Close")
        close.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogCancelButton))
        close.clicked.connect(self.accept)
        print_button.setObjectName("primaryClassic")
        png.setObjectName("primaryClassic")
        top_buttons.addWidget(print_button, 0, 0); top_buttons.addWidget(close, 0, 1); top_buttons.addWidget(png, 1, 0)
        left.addLayout(top_buttons)

        period = QGroupBox("From")
        p_grid = QGridLayout(period)
        self.period_group = QButtonGroup(self)
        periods = [
            ("All", "all", 0, 0), ("Specific Day", "specific", 1, 0), ("Date Range", "range", 2, 0),
            ("Today", "today", 0, 2), ("Yesterday", "yesterday", 1, 2), ("Last 7 Days", "last7", 2, 2),
            ("Last 28 Days", "last28", 3, 2), ("This Month", "month", 4, 2), ("Last Month", "lastmonth", 5, 2),
        ]
        for label, key, row, col in periods:
            radio = QRadioButton(label)
            radio.setProperty("value", key)
            self.period_group.addButton(radio)
            p_grid.addWidget(radio, row, col)
        self.period_group.buttons()[0].setChecked(True)
        self.start = _date_edit(date.today() - timedelta(days=30))
        self.end = _date_edit(date.today())
        p_grid.addWidget(self.start, 3, 0, 1, 2); p_grid.addWidget(self.end, 4, 0, 1, 2)
        left.addWidget(period)

        show_group = QGroupBox("Show")
        show_layout = QHBoxLayout(show_group)
        self.show_group = QButtonGroup(self)
        for label, key in (("All", "all"), ("Good", "good"), ("Bad", "bad")):
            radio = QRadioButton(label); radio.setProperty("value", key); self.show_group.addButton(radio); show_layout.addWidget(radio)
        self.show_group.buttons()[0].setChecked(True)
        left.addWidget(show_group)

        serial_group = QGroupBox("")
        serial_layout = QHBoxLayout(serial_group)
        self.unique_only = QRadioButton("Unique Serial Only")
        self.all_serials = QRadioButton("All Serials"); self.all_serials.setChecked(True)
        serial_layout.addWidget(self.unique_only); serial_layout.addWidget(self.all_serials)
        left.addWidget(serial_group)

        selection = QHBoxLayout()
        plot_type_box = QGroupBox("Plot Type")
        plot_type_layout = QVBoxLayout(plot_type_box)
        self.plot_type_group = QButtonGroup(self)
        for label, key in (("Histogram", "histogram"), ("Scatter Plot", "scatter"), ("Cross Plot", "crossplot"), ("Numerics", "numerics"), ("Statistics", "statistics")):
            radio = QRadioButton(label); radio.setProperty("value", key); self.plot_type_group.addButton(radio); plot_type_layout.addWidget(radio)
            radio.toggled.connect(lambda _checked=False: self.refresh())
        self.plot_type_group.buttons()[0].setChecked(True)
        selection.addWidget(plot_type_box)

        self.measure_box = QGroupBox("Histogram")
        measure_layout = QVBoxLayout(self.measure_box)
        self.measure_group = QButtonGroup(self)
        self.measure_checks: dict[str, QCheckBox] = {}
        for field_name in MEASUREMENT_FIELDS:
            radio = QRadioButton(MEASUREMENT_LABELS[field_name])
            radio.setProperty("value", field_name)
            self.measure_group.addButton(radio)
            measure_layout.addWidget(radio)
            check = QCheckBox(MEASUREMENT_LABELS[field_name])
            check.setChecked(field_name != "temperature")
            check.setVisible(False)
            self.measure_checks[field_name] = check
            measure_layout.addWidget(check)
        for button in self.measure_group.buttons():
            if button.property("value") == "resistance":
                button.setChecked(True)
        self.x_field = QComboBox(); self.y_field = QComboBox()
        for field_name in MEASUREMENT_FIELDS:
            self.x_field.addItem(MEASUREMENT_LABELS[field_name], field_name)
            self.y_field.addItem(MEASUREMENT_LABELS[field_name], field_name)
        self.x_field.setCurrentIndex(MEASUREMENT_FIELDS.index("resistance"))
        self.y_field.setCurrentIndex(MEASUREMENT_FIELDS.index("frequency"))
        measure_layout.addWidget(QLabel("Cross Plot X")); measure_layout.addWidget(self.x_field)
        measure_layout.addWidget(QLabel("Cross Plot Y")); measure_layout.addWidget(self.y_field)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        measure_layout.addWidget(refresh)
        selection.addWidget(self.measure_box)
        left.addLayout(selection)
        left.addStretch(1)
        left_panel = QWidget(); left_panel.setObjectName("classicPage"); left_panel.setLayout(left); left_panel.setFixedWidth(245)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(265)
        left_scroll.setMaximumWidth(285)
        left_scroll.setWidget(left_panel)
        body.addWidget(left_scroll)

        self.output_stack = QStackedWidget()
        self.plot = pg.PlotWidget(background="w")
        self.plot.showGrid(x=True, y=True, alpha=0.22)
        self.output_stack.addWidget(self.plot)
        self.numeric_table = QTableWidget(0, 13)
        self.numeric_table.setHorizontalHeaderLabels(["Date", "String", "Tester", "Status", "Model"] + [MEASUREMENT_LABELS[f] for f in MEASUREMENT_FIELDS])
        _prep_table(self.numeric_table)
        self.output_stack.addWidget(self.numeric_table)
        self.statistics_text = QPlainTextEdit(); self.statistics_text.setReadOnly(True)
        mono = QFont("Courier New"); mono.setStyleHint(QFont.StyleHint.Monospace); self.statistics_text.setFont(mono)
        self.output_stack.addWidget(self.statistics_text)
        body.addWidget(self.output_stack, 1)
        root.addLayout(body, 1)
        self.plot_type_group.buttonToggled.connect(lambda *_: self._update_measure_controls())
        self.period_group.buttonToggled.connect(lambda *_: self._update_date_controls())
        self.show_group.buttonToggled.connect(lambda *_: self.refresh())
        self.unique_only.toggled.connect(lambda *_: self.refresh())
        self.all_serials.toggled.connect(lambda *_: self.refresh())
        for check in self.measure_checks.values():
            check.toggled.connect(lambda *_: self.refresh())
        self.measure_group.buttonToggled.connect(lambda *_: self.refresh())
        self.x_field.currentIndexChanged.connect(lambda *_: self.refresh())
        self.y_field.currentIndexChanged.connect(lambda *_: self.refresh())
        self._update_measure_controls()
        self._update_date_controls()
        self.refresh()
        QTimer.singleShot(0, self._position_on_screen)

    def _position_on_screen(self) -> None:
        _fit_dialog_to_screen(self, 1180, 720)
        _center_on_parent_or_screen(self)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._position_on_screen)

    @staticmethod
    def _checked_value(group: QButtonGroup, default: str) -> str:
        button = group.checkedButton()
        return str(button.property("value")) if button else default

    def _update_date_controls(self) -> None:
        key = self._checked_value(self.period_group, "all")
        self.start.setEnabled(key in {"specific", "range"})
        self.end.setEnabled(key == "range")

    def _date_range(self) -> tuple[date | None, date | None]:
        key = self._checked_value(self.period_group, "all")
        today = date.today()
        if key == "all":
            return None, None
        if key == "today":
            return today, today
        if key == "yesterday":
            value = today - timedelta(days=1); return value, value
        if key == "last7":
            return today - timedelta(days=6), today
        if key == "last28":
            return today - timedelta(days=27), today
        if key == "month":
            return today.replace(day=1), today
        if key == "lastmonth":
            first = today.replace(day=1)
            previous_end = first - timedelta(days=1)
            return previous_end.replace(day=1), previous_end
        if key == "specific":
            value = _qdate_to_date(self.start.date()); return value, value
        return _qdate_to_date(self.start.date()), _qdate_to_date(self.end.date())

    def _selected_rows(self) -> list[dict[str, Any]]:
        start, end = self._date_range()
        rows = self.database.query_records(start=start, end=end, result="All", limit=None, ascending=True)
        mode = self._checked_value(self.show_group, "all")
        if mode == "good":
            rows = [row for row in rows if row["status"] == "PASS"]
        elif mode == "bad":
            rows = [row for row in rows if row["status"] != "PASS"]
        if self.unique_only.isChecked():
            latest: dict[str, dict[str, Any]] = {}
            for row in rows:
                identity = str(row["serial"] or row["string_no"] or "")
                if identity:
                    latest[identity] = row
            rows = list(latest.values())
        return rows

    def _update_measure_controls(self) -> None:
        plot_type = self._checked_value(self.plot_type_group, "histogram")
        self.measure_box.setTitle("Show" if plot_type == "scatter" else "Histogram")
        for radio in self.measure_group.buttons():
            radio.setVisible(plot_type == "histogram")
        for check in self.measure_checks.values():
            check.setVisible(plot_type == "scatter")
        self.x_field.setVisible(plot_type == "crossplot")
        self.y_field.setVisible(plot_type == "crossplot")
        # The preceding labels are kept in the layout; hide them by disabling when not relevant.
        self.x_field.setEnabled(plot_type == "crossplot")
        self.y_field.setEnabled(plot_type == "crossplot")

    def refresh(self) -> None:
        if not hasattr(self, "plot"):
            return
        self.rows = self._selected_rows()
        plot_type = self._checked_value(self.plot_type_group, "histogram")
        if plot_type == "numerics":
            self.output_stack.setCurrentWidget(self.numeric_table)
            self._fill_numerics()
            return
        if plot_type == "statistics":
            self.output_stack.setCurrentWidget(self.statistics_text)
            start, end = self._date_range()
            self.statistics_text.setPlainText(_statistics_text(self.database, self.database.statistics(start=start, end=end)))
            return
        self.output_stack.setCurrentWidget(self.plot)
        self.plot.clear()
        if plot_type == "histogram":
            self._histogram()
        elif plot_type == "scatter":
            self._scatter()
        else:
            self._crossplot()

    def _histogram(self) -> None:
        field_name = self._checked_value(self.measure_group, "resistance")
        values = np.asarray([float(row[field_name]) for row in self.rows if row[field_name] is not None], dtype=float)
        self.plot.setBackground("#FFFFFF")
        self.plot.setTitle(MEASUREMENT_LABELS[field_name])
        self.plot.setLabel("left", "Count")
        self.plot.setLabel("bottom", MEASUREMENT_LABELS[field_name])
        if values.size:
            counts, edges = np.histogram(values, bins=self.config.histogram_bins)
            self.plot.addItem(pg.BarGraphItem(x=(edges[:-1] + edges[1:]) / 2, height=counts, width=np.diff(edges) * 0.93, brush="#4FA3E3", pen="#1F5D8A"))
        limit = self.config.limits[field_name]
        for value, label in ((limit.minimum, "Min"), (limit.nominal, "Nom"), (limit.maximum, "Max")):
            if value is not None:
                line = pg.InfiniteLine(pos=float(value), angle=90, pen=pg.mkPen("#D33F49", width=2), label=f"{label} {value:g}")
                self.plot.addItem(line)
        failures = sum(1 for row in self.rows if row["status"] == "FAIL")
        self.plot.setTitle(f"{MEASUREMENT_LABELS[field_name]}   Entries: {len(values):,}   Failures: {failures:,}")

    def _scatter(self) -> None:
        self.plot.setBackground("w")
        try:
            if getattr(self.plot.plotItem, "legend", None) is not None:
                self.plot.plotItem.legend.scene().removeItem(self.plot.plotItem.legend)
                self.plot.plotItem.legend = None
        except Exception:
            pass
        palette = [self.config.limits[field].color for field in MEASUREMENT_FIELDS]
        for idx, field_name in enumerate(MEASUREMENT_FIELDS):
            if not self.measure_checks[field_name].isChecked():
                continue
            points = [(i, row[field_name]) for i, row in enumerate(self.rows) if row[field_name] is not None]
            if not points:
                continue
            x = np.asarray([p[0] for p in points], dtype=float)
            y = np.asarray([float(p[1]) for p in points], dtype=float)
            self.plot.plot(x, y, pen=None, symbol="o", symbolSize=3, symbolBrush=palette[idx], name=MEASUREMENT_LABELS[field_name])
        if self.rows:
            self.plot.addLegend(offset=(8, 8))
        self.plot.setTitle(f"Scatter Plot - {len(self.rows):,} Records")
        self.plot.setLabel("bottom", "Test sequence")

    def _crossplot(self) -> None:
        self.plot.setBackground("w")
        x_field = str(self.x_field.currentData())
        y_field = str(self.y_field.currentData())
        members = [row for row in self.rows if row[x_field] is not None and row[y_field] is not None]
        if members:
            x = np.asarray([float(row[x_field]) for row in members], dtype=float)
            y = np.asarray([float(row[y_field]) for row in members], dtype=float)
            self.plot.plot(x, y, pen=None, symbol="o", symbolSize=4, symbolBrush="#70E890", symbolPen="#3FBF68")
        self.plot.setTitle("CrossPlot")
        self.plot.setLabel("bottom", MEASUREMENT_LABELS[x_field])
        self.plot.setLabel("left", MEASUREMENT_LABELS[y_field])
        x_limit = self.config.limits[x_field]
        y_limit = self.config.limits[y_field]
        for value in (x_limit.minimum, x_limit.maximum):
            if value is not None:
                self.plot.addItem(pg.InfiniteLine(pos=float(value), angle=90, pen=pg.mkPen("#808080")))
        for value in (y_limit.minimum, y_limit.maximum):
            if value is not None:
                self.plot.addItem(pg.InfiniteLine(pos=float(value), angle=0, pen=pg.mkPen("#808080")))

    def _export_current_png(self) -> None:
        if self.output_stack.currentWidget() is self.plot:
            _export_plot_png(self.plot, self, "smt_results.png")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "smt_results_view.png", "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if not self.output_stack.currentWidget().grab().save(path, "PNG"):
            QMessageBox.critical(self, "SMTAN2", "Unable to export the current result view.")

    def _fill_numerics(self) -> None:
        self.numeric_table.setSortingEnabled(False)
        self.numeric_table.setRowCount(0)
        for data in self.rows:
            row = self.numeric_table.rowCount(); self.numeric_table.insertRow(row)
            values = [data["tested_at"], data["string_no"] or data["serial"], data["tester"], data["status"], data["model"]] + [data[f] for f in MEASUREMENT_FIELDS]
            for col, value in enumerate(values):
                self.numeric_table.setItem(row, col, QTableWidgetItem(_format_number(value)))
        self.numeric_table.setSortingEnabled(True)
        self.numeric_table.verticalHeader().setDefaultSectionSize(20)
        self.numeric_table.resizeColumnsToContents()


class StatisticsDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Statistics")
        self.resize(900, 590)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("Statistics"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        go = QPushButton("Go"); go.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogApplyButton)); go.clicked.connect(self.refresh)
        left.addWidget(go)
        range_box = QGroupBox("Range")
        range_layout = QVBoxLayout(range_box)
        self.all_records = QRadioButton("All"); self.all_records.setChecked(True)
        self.specified = QRadioButton("Specified Range")
        range_layout.addWidget(self.all_records); range_layout.addWidget(self.specified)
        self.start = _date_edit(date.today() - timedelta(days=30)); self.end = _date_edit(date.today())
        range_layout.addWidget(QLabel("From")); range_layout.addWidget(self.start); range_layout.addWidget(QLabel("To")); range_layout.addWidget(self.end)
        left.addWidget(range_box)
        clipboard = QPushButton("To Clipboard"); clipboard.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        missing = QPushButton("Missing Strings"); missing.clicked.connect(lambda: UnseenStringsDialog(database, self).exec())
        graph = QPushButton("Failure Graph"); graph.clicked.connect(lambda: self.stack.setCurrentWidget(self.plot))
        report = QPushButton("Statistics Report"); report.clicked.connect(lambda: self.stack.setCurrentWidget(self.text))
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        for button in (clipboard, missing, graph, report, close):
            button.setMinimumHeight(36); left.addWidget(button)
        left.addStretch(1)
        left_widget = QWidget(); left_widget.setObjectName("classicPage"); left_widget.setLayout(left); left_widget.setFixedWidth(200)
        body.addWidget(left_widget)
        self.stack = QStackedWidget()
        self.text = QPlainTextEdit(); self.text.setReadOnly(True); self.text.setFont(QFont("Courier New"))
        self.plot = pg.PlotWidget(background="#BFEFF2")
        self.plot.showGrid(x=False, y=True, alpha=0.2)
        self.stack.addWidget(self.text); self.stack.addWidget(self.plot)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.refresh()

    def refresh(self) -> None:
        start = None if self.all_records.isChecked() else _qdate_to_date(self.start.date())
        end = None if self.all_records.isChecked() else _qdate_to_date(self.end.date())
        stats = self.database.statistics(start=start, end=end)
        self.text.setPlainText(_statistics_text(self.database, stats))
        self.plot.clear()
        items = sorted(stats["failure_counts"].items(), key=lambda item: int(item[1]), reverse=True)
        if items:
            values = np.asarray([int(count) for _, count in items], dtype=float)
            labels = [MEASUREMENT_LABELS.get(name, name.replace("_", " ").title()) for name, _ in items]
            self.plot.addItem(pg.BarGraphItem(x=np.arange(len(values)), height=values, width=0.72, brush="#00E83A", pen="#008000"))
            self.plot.getAxis("bottom").setTicks([[(float(i), label[:12]) for i, label in enumerate(labels)]])
        self.plot.setTitle("Breakdown of Failures")
        self.plot.setLabel("left", "Failure Count")
        self.stack.setCurrentWidget(self.text)


class MaintenanceDialog(QDialog):
    MODES = [
        ("Remove Duplicates", "duplicates"), ("Remove a File", "file"), ("Remove an SMT", "tester"),
        ("Remove by Result", "result"), ("Remove a String", "string"), ("Remove a Date", "date"),
        ("Remove SMT Model", "model"),
    ]

    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("DB Maintenance")
        self.resize(650, 510)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("DB Maintenance"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.group = QButtonGroup(self)
        for label, key in self.MODES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("value", key)
            button.setIcon(_icon(self, QStyle.StandardPixmap.SP_DriveHDIcon))
            button.setMinimumHeight(36)
            button.clicked.connect(self._refresh_values)
            self.group.addButton(button)
            left.addWidget(button)
        self.group.buttons()[0].setChecked(True)
        body.addLayout(left)
        self.values = QListWidget()
        body.addWidget(self.values, 1)
        right = QVBoxLayout()
        go = QPushButton("Go"); go.setIcon(_icon(self, QStyle.StandardPixmap.SP_ArrowDown)); go.setMinimumSize(112, 44); go.clicked.connect(self._execute)
        close = QPushButton("Close"); close.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogCloseButton)); close.setMinimumSize(112, 44); close.clicked.connect(self.accept)
        right.addWidget(go); right.addStretch(1); right.addWidget(close)
        body.addLayout(right)
        root.addLayout(body, 1)
        root.addWidget(QLabel("Select an item then click 'Go'"), 0, Qt.AlignmentFlag.AlignCenter)
        self._refresh_values()

    def _operation(self) -> str:
        button = self.group.checkedButton()
        return str(button.property("value")) if button else "duplicates"

    def _refresh_values(self) -> None:
        self.values.clear()
        mode = self._operation()
        if mode == "duplicates":
            self.values.addItem("Remove duplicate source rows, keeping the latest record")
        else:
            for value in self.database.maintenance_values(mode):
                self.values.addItem(str(value))

    def _execute(self) -> None:
        mode = self._operation()
        value = ""
        if mode != "duplicates":
            item = self.values.currentItem()
            if item is None:
                QMessageBox.information(self, "SMTAN2", "Select a value first.")
                return
            value = item.text()
        if QMessageBox.question(self, "SMTAN2", "This operation permanently deletes database records. Continue?") != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.database.maintenance_delete(mode, value)
            QMessageBox.information(self, "SMTAN2", f"{count:,} record(s) removed.")
            self._refresh_values()
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", str(exc))


class PendingRetestsDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Pending Retests")
        self.resize(960, 560)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("Pending Retests"))
        selectors = QHBoxLayout()
        for label, callback in (("Select All", lambda: self._set_checks(Qt.CheckState.Checked)), ("Select None", lambda: self._set_checks(Qt.CheckState.Unchecked)), ("Invert Selection", self._invert_checks)):
            button = QPushButton(label); button.clicked.connect(callback); selectors.addWidget(button)
        selectors.addStretch(1)
        root.addLayout(selectors)
        body = QHBoxLayout()
        left = QVBoxLayout()
        update = QPushButton("Update"); update.clicked.connect(self.refresh)
        list_button = QPushButton("List"); list_button.clicked.connect(self._export)
        remove = QPushButton("Remove Selected"); remove.clicked.connect(self._remove_selected)
        restore = QPushButton("Restore Excluded"); restore.clicked.connect(self._restore_selected)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.accept)
        for button in (update, list_button, remove, restore, cancel):
            button.setMinimumSize(130, 40); left.addWidget(button)
        left.addStretch(1)
        body.addLayout(left)
        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels([
            "Select", "String", "Serial", "Tester", "SMT Model", "SMT Serial", "First Failed", "Last Test", "Resistance",
            "Frequency", "Damping", "Impedance", "Failure",
        ])
        _prep_table(self.table, checkbox_rows=True)
        body.addWidget(self.table, 1)
        root.addLayout(body, 1)
        self.summary = QLabel()
        root.addWidget(self.summary)
        self.refresh()

    def refresh(self) -> None:
        rows = self.database.pending_retests(include_excluded=True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for data in rows:
            row = self.table.rowCount(); self.table.insertRow(row)
            check = QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable); check.setCheckState(Qt.CheckState.Unchecked)
            identity = str(data["string_no"] or data["serial"])
            check.setData(Qt.ItemDataRole.UserRole, identity)
            self.table.setItem(row, 0, check)
            values = [
                data["string_no"], data["serial"], data["tester"], data["model"], data.get("operator", ""), data.get("first_failed_at", ""),
                data["tested_at"], data["resistance"], data["frequency"], data["damping"], data["impedance"], ", ".join(data.get("failure_flags", [])),
            ]
            for col, value in enumerate(values, start=1):
                self.table.setItem(row, col, QTableWidgetItem(_format_number(value)))
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        active = self.database.pending_retests()
        self.summary.setText(f"{len(active):,} active pending retest(s); columns may be sorted by clicking a header.")

    def _checked(self) -> list[str]:
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                result.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return result

    def _set_checks(self, state: Qt.CheckState) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(state)

    def _invert_checks(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _remove_selected(self) -> None:
        identities = self._checked()
        if identities:
            self.database.exclude_pending(identities)
            self.refresh()

    def _restore_selected(self) -> None:
        identities = self._checked()
        if identities:
            self.database.restore_pending(identities)
            self.refresh()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Pending Retests List", str(self.database.path.with_name(self.database.path.stem + "_pending_retests.csv")), "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([self.table.horizontalHeaderItem(c).text() for c in range(1, self.table.columnCount())])
            for row in range(self.table.rowCount()):
                writer.writerow([self.table.item(row, c).text() if self.table.item(row, c) else "" for c in range(1, self.table.columnCount())])


class SingleStringDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.config = database.load_configuration()
        self.rows: list[dict[str, Any]] = []
        self.setWindowTitle("Single String Display")
        self.resize(1000, 600)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("Single String Display"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        go = QPushButton("Go"); go.clicked.connect(self.refresh)
        png = QPushButton("PNG"); png.clicked.connect(lambda: _export_plot_png(self.plot, self, "smt_single_string.png"))
        print_button = QPushButton("Print"); print_button.clicked.connect(lambda: _print_widget(self.plot, self))
        analysis = QPushButton("Analysis"); analysis.clicked.connect(self._analysis)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        for button in (go, png, print_button, analysis, close):
            button.setMinimumSize(112, 36); left.addWidget(button)
        left.addStretch(1)
        body.addLayout(left)
        right = QVBoxLayout()
        self.plot = pg.PlotWidget(background="w")
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        right.addWidget(self.plot, 1)
        controls = QGridLayout()
        self.measurement = QComboBox()
        for field_name in MEASUREMENT_FIELDS:
            self.measurement.addItem(MEASUREMENT_LABELS[field_name], field_name)
        self.measurement.setCurrentIndex(MEASUREMENT_FIELDS.index("frequency"))
        self.string_1 = QLineEdit(self.config.reference_string_1)
        self.string_2 = QLineEdit(self.config.reference_string_2)
        self.all_dates = QRadioButton("All"); self.all_dates.setChecked(True)
        self.selected_dates = QRadioButton("Selected Dates")
        self.start = _date_edit(date.today() - timedelta(days=30)); self.end = _date_edit(date.today())
        controls.addWidget(QLabel("Show"), 0, 0); controls.addWidget(self.measurement, 0, 1)
        controls.addWidget(QLabel("String 1"), 1, 0); controls.addWidget(self.string_1, 1, 1)
        controls.addWidget(QLabel("String 2"), 2, 0); controls.addWidget(self.string_2, 2, 1)
        controls.addWidget(self.all_dates, 1, 2); controls.addWidget(self.selected_dates, 1, 3)
        controls.addWidget(QLabel("From"), 2, 2); controls.addWidget(self.start, 2, 3); controls.addWidget(QLabel("To"), 2, 4); controls.addWidget(self.end, 2, 5)
        right.addLayout(controls)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        self.refresh()

    def refresh(self) -> None:
        field_name = str(self.measurement.currentData())
        start = None if self.all_dates.isChecked() else _qdate_to_date(self.start.date())
        end = None if self.all_dates.isChecked() else _qdate_to_date(self.end.date())
        self.rows = []
        for identity in [self.string_1.text().strip(), self.string_2.text().strip()]:
            if identity:
                self.rows.extend(self.database.single_string_history([identity], start=start, end=end))
        self.plot.clear()
        palette = ["#0066CC", "#FF0000", "#00A000", "#B000B0", "#FF8800", "#00A0A0", "#404040"]
        testers = sorted({str(row["tester"] or "Unknown") for row in self.rows})
        for index, tester in enumerate(testers):
            members = [row for row in self.rows if str(row["tester"] or "Unknown") == tester and row[field_name] is not None]
            x = np.arange(len(members), dtype=float)
            y = np.asarray([float(row[field_name]) for row in members], dtype=float)
            if len(y):
                self.plot.plot(x, y, pen=pg.mkPen(palette[index % len(palette)], width=1), symbol="o", symbolSize=4, symbolBrush=palette[index % len(palette)], name=tester)
        if testers:
            self.plot.addLegend()
        limit = self.config.limits[field_name]
        for value in (limit.minimum, limit.maximum):
            if value is not None:
                self.plot.addItem(pg.InfiniteLine(pos=float(value), angle=0, pen=pg.mkPen("#FF8080")))
        self.plot.setTitle(MEASUREMENT_LABELS[field_name])
        self.plot.setLabel("left", MEASUREMENT_LABELS[field_name])
        self.plot.setLabel("bottom", "Test sequence")

    def _analysis(self) -> None:
        field_name = str(self.measurement.currentData())
        groups: dict[str, list[float]] = {}
        for row in self.rows:
            if row[field_name] is not None:
                groups.setdefault(str(row["tester"] or "Unknown"), []).append(float(row[field_name]))
        lines = [f"Analysis of {MEASUREMENT_LABELS[field_name]}", ""]
        for tester, values in sorted(groups.items()):
            lines.append(f"{tester}: n={len(values)}, mean={mean(values):.6g}, std={pstdev(values) if len(values)>1 else 0:.6g}, min={min(values):.6g}, max={max(values):.6g}")
        if not groups:
            lines.append("No numeric data in the selected range.")
        QMessageBox.information(self, "SMTAN2", "\n".join(lines))


class TimeAnalysisDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Time Analysis")
        self.resize(1000, 620)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("Time Analysis"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        go = QPushButton("Go"); go.clicked.connect(self.refresh)
        png = QPushButton("PNG"); png.clicked.connect(lambda: _export_plot_png(self.plot, self, "smt_time_analysis.png"))
        print_button = QPushButton("Print"); print_button.clicked.connect(lambda: _print_widget(self.plot, self))
        list_button = QPushButton("List"); list_button.clicked.connect(lambda: self.table.setVisible(not self.table.isVisible()))
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        for button in (go, png, print_button, list_button, close):
            button.setMinimumSize(112, 36); left.addWidget(button)
        left.addStretch(1)
        body.addLayout(left)
        right = QVBoxLayout()
        self.plot = pg.PlotWidget(background="#BFEFF2")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        right.addWidget(self.plot, 2)
        controls = QHBoxLayout()
        self.measurement = QComboBox(); self.measurement.addItem("Number of tests per day", "tests")
        for field_name in MEASUREMENT_FIELDS:
            self.measurement.addItem(MEASUREMENT_LABELS[field_name], field_name)
        self.all_dates = QRadioButton("All"); self.all_dates.setChecked(True)
        self.selected_dates = QRadioButton("Selected Dates")
        self.start = _date_edit(date.today() - timedelta(days=30)); self.end = _date_edit(date.today())
        controls.addWidget(QLabel("Show")); controls.addWidget(self.measurement); controls.addWidget(self.all_dates); controls.addWidget(self.selected_dates)
        controls.addWidget(QLabel("From")); controls.addWidget(self.start); controls.addWidget(QLabel("To")); controls.addWidget(self.end)
        right.addLayout(controls)
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels(["Date", "Tests", "Unique", "Pass", "Warn", "Fail"] + [MEASUREMENT_LABELS[f] for f in MEASUREMENT_FIELDS])
        _prep_table(self.table)
        right.addWidget(self.table, 1)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        self.refresh()

    def refresh(self) -> None:
        start = None if self.all_dates.isChecked() else _qdate_to_date(self.start.date())
        end = None if self.all_dates.isChecked() else _qdate_to_date(self.end.date())
        field_name = str(self.measurement.currentData())
        rows = self.database.time_analysis(field_name, start=start, end=end)
        self.plot.clear()
        x = np.arange(len(rows), dtype=float)
        if field_name == "tests":
            y = np.asarray([row["tests"] for row in rows], dtype=float)
            self.plot.addItem(pg.BarGraphItem(x=x, height=y, width=0.72, brush="#00E83A", pen="#008000"))
            self.plot.setTitle("Tests by Day -> All Records")
            self.plot.setLabel("left", "Tests")
        else:
            y = np.asarray([np.nan if row[field_name] is None else float(row[field_name]) for row in rows], dtype=float)
            valid = np.isfinite(y)
            self.plot.plot(x[valid], y[valid], pen=pg.mkPen("#0000CC", width=1), symbol="o", symbolSize=4, symbolBrush="#0000CC")
            self.plot.setTitle(f"Daily Mean {MEASUREMENT_LABELS[field_name]}")
            self.plot.setLabel("left", MEASUREMENT_LABELS[field_name])
        if rows:
            step = max(1, len(rows) // 12)
            self.plot.getAxis("bottom").setTicks([[(float(i), row["date"]) for i, row in enumerate(rows) if i % step == 0]])
        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        for data in rows:
            row = self.table.rowCount(); self.table.insertRow(row)
            values = [data["date"], data["tests"], data["unique_strings"], data["pass"], data["warn"], data["fail"]] + [data[f] for f in MEASUREMENT_FIELDS]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(_format_number(value)))
        self.table.setSortingEnabled(True); self.table.resizeColumnsToContents()


class UnseenStringsDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Unseen Strings")
        self.resize(680, 540)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("Unseen Strings"))
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Strings not seen since"))
        self.since = _date_edit(date.today() - timedelta(days=30)); controls.addWidget(self.since)
        go = QPushButton("Go"); go.clicked.connect(self.refresh); controls.addWidget(go)
        missing = QPushButton("Missing Strings"); missing.clicked.connect(self._show_missing); controls.addWidget(missing)
        copy = QPushButton("To Clipboard"); copy.clicked.connect(self._copy); controls.addWidget(copy)
        close = QPushButton("Close"); close.clicked.connect(self.accept); controls.addWidget(close)
        root.addLayout(controls)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["String", "Last Seen", "Days Unseen"])
        _prep_table(self.table)
        root.addWidget(self.table, 1)
        self.missing_list = QListWidget(); self.missing_list.setVisible(False)
        root.addWidget(self.missing_list, 1)
        self.summary = QLabel(); root.addWidget(self.summary)
        self.refresh()

    def refresh(self) -> None:
        rows = self.database.unseen_strings(_qdate_to_date(self.since.date()))
        self.table.setRowCount(0)
        for data in rows:
            row = self.table.rowCount(); self.table.insertRow(row)
            for col, value in enumerate((data["string_no"], data["last_seen"], data["days_unseen"])):
                self.table.setItem(row, col, QTableWidgetItem(_format_number(value)))
        self.table.resizeColumnsToContents()
        self.table.setVisible(True); self.missing_list.setVisible(False)
        self.summary.setText(f"Total number of strings outstanding since {_qdate_to_date(self.since.date()).isoformat()} is {len(rows):,}")

    def _show_missing(self) -> None:
        values = self.database.missing_strings()
        self.missing_list.clear(); self.missing_list.addItems(values)
        self.table.setVisible(False); self.missing_list.setVisible(True)
        self.summary.setText(f"{len(values):,} missing string ID(s) in the configured range")

    def _copy(self) -> None:
        if self.table.isVisible():
            lines = ["\t".join(self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(3)) for r in range(self.table.rowCount())]
        else:
            lines = [self.missing_list.item(i).text() for i in range(self.missing_list.count())]
        QApplication.clipboard().setText("\n".join(lines))


class UtilitiesDialog(QDialog):
    def __init__(self, database: SmtProjectDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Utilities")
        self.resize(510, 430)
        _set_classic(self)
        root = QVBoxLayout(self)
        root.addWidget(_classic_title("Utilities"))
        actions = [
            ("Single String Query", lambda: SingleStringDialog(database, self).exec(), QStyle.StandardPixmap.SP_FileDialogContentsView),
            ("Time Analysis", lambda: TimeAnalysisDialog(database, self).exec(), QStyle.StandardPixmap.SP_ComputerIcon),
            ("Statistics", lambda: StatisticsDialog(database, self).exec(), QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("Pending Retests", lambda: PendingRetestsDialog(database, self).exec(), QStyle.StandardPixmap.SP_MessageBoxWarning),
            ("Unseen / Missing Strings", lambda: UnseenStringsDialog(database, self).exec(), QStyle.StandardPixmap.SP_FileDialogListView),
            ("Database Records", lambda: RecordsDialog(database, self).exec(), QStyle.StandardPixmap.SP_DriveHDIcon),
            ("Database Maintenance", lambda: MaintenanceDialog(database, self).exec(), QStyle.StandardPixmap.SP_ComputerIcon),
        ]
        for label, callback, pixmap in actions:
            button = QPushButton(label)
            button.setObjectName("largeClassic")
            button.setIcon(_icon(self, pixmap))
            button.clicked.connect(callback)
            root.addWidget(button)
        close = QPushButton("Close"); close.clicked.connect(self.accept); root.addWidget(close)
