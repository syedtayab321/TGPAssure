from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.magnetic.models import MagneticSurveyType
from modules.magnetic.reader import MagneticReader
from core.visualization.palette_library import DEFAULT_PALETTE, palette_hex
from ui.widgets.color_palette_dialog import PaletteSelectorButton


_DIALOG_QSS = """
QDialog {
    background: #F5F7FA;
}
QFrame#headerCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #F7FBFE, stop:1 #EAF5FB);
    border: 1px solid #BFD9E7;
    border-left: 4px solid #1687B8;
    border-radius: 8px;
}
QFrame#infoCard,
QFrame#noticeCard {
    background: #FFFFFF;
    border: 1px solid #D8E1E8;
    border-radius: 8px;
}
QFrame#noticeCard {
    background: #FFF8E6;
    border-color: #E5C86D;
}
QLabel#dialogTitle {
    color: #0C3852;
    font-size: 16px;
    font-weight: 700;
}
QLabel#dialogSubtitle {
    color: #5E7182;
    font-size: 10px;
}
QLabel#sectionTitle {
    color: #173A52;
    font-size: 11px;
    font-weight: 700;
}
QLabel#statusPill {
    background: #E8F4EC;
    color: #167044;
    border: 1px solid #B9DEC7;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#mutedLabel {
    color: #66798A;
}
QTabWidget::pane {
    border: 1px solid #D7E0E7;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: #EEF2F6;
    color: #455A6C;
    border: 1px solid #D7E0E7;
    padding: 8px 16px;
    min-width: 105px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #0B6FA4;
    border-bottom-color: #FFFFFF;
    border-top: 3px solid #1687B8;
    padding-top: 6px;
    font-weight: 700;
}
QTabBar::tab:hover:!selected {
    background: #E5EEF5;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7F9FB;
    border: 0;
    gridline-color: #E4EAF0;
    selection-background-color: #DCEEF8;
    selection-color: #18384E;
}
QHeaderView::section {
    background: #EDF2F6;
    color: #344B5E;
    border: 0;
    border-bottom: 1px solid #D8E1E8;
    padding: 6px;
    font-weight: 700;
}
QLineEdit,
QComboBox {
    min-height: 28px;
    border: 1px solid #C9D5DF;
    border-radius: 4px;
    background: #FFFFFF;
    padding: 2px 7px;
}
QLineEdit:disabled,
QComboBox:disabled {
    color: #81909D;
    background: #EEF2F5;
}
QSpinBox {
    min-height: 28px;
    border: 1px solid #C9D5DF;
    border-radius: 4px;
    background: #FFFFFF;
    padding: 2px 7px;
}
QPushButton {
    min-height: 28px;
    padding: 3px 14px;
    border: 1px solid #B9C8D4;
    border-radius: 5px;
    background: #FFFFFF;
    color: #18384E;
    font-weight: 700;
}
QPushButton:hover {
    border-color: #1687B8;
    background: #EEF8FD;
}
QPushButton#primaryButton {
    background: #1687B8;
    border-color: #0D6E98;
    color: #FFFFFF;
}
"""


_CANONICAL_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("total_field", "Total magnetic field / TMI", True),
    ("timestamp", "Timestamp", False),
    ("date", "Date", False),
    ("time", "Time", False),
    ("x", "X / Easting / Longitude", False),
    ("y", "Y / Northing / Latitude", False),
    ("elevation", "Elevation / GPS height", False),
    ("line_id", "Line ID", False),
    ("station_id", "Station / Fiducial", False),
    ("line_type", "Line type", False),
    ("base_field", "Base magnetic field", False),
    ("sensor_1", "Sensor 1", False),
    ("sensor_2", "Sensor 2", False),
    ("gps_quality", "GPS quality / fix", False),
    ("gps_hdop", "GPS HDOP", False),
    ("satellites", "Satellites", False),
    ("temperature", "Temperature", False),
    ("heading", "Heading / azimuth", False),
    ("speed", "Speed", False),
)


class MagneticImportDialog(QDialog):
    """Review-first import dialog for magnetic datasets.

    The dialog deliberately avoids requiring GIS expertise. When the reader
    confidently detects a CRS, that CRS is selected automatically. If the CRS
    is unknown, the user can still import the dataset and spatially dependent
    QC stages can be skipped until a CRS is assigned later.
    """

    def __init__(
        self,
        inspection: dict[str, Any],
        *,
        importing_base: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inspection = dict(inspection)
        self.importing_base = importing_base
        self._layout_skip_rows_value = int(self.inspection.get("skip_rows", 0) or 0)
        self._layout_skip_columns_value = str(self.inspection.get("skip_columns", "") or "")
        self.mapping_combos: dict[str, QComboBox] = {}
        self.setWindowTitle("Magnetic Data Import")
        self.resize(790, 575)
        self.setMinimumSize(700, 500)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()

    @property
    def skip_rows(self) -> int:
        spin = getattr(self, "skip_rows_spin", None)
        if spin is not None:
            return int(spin.value())
        return int(self._layout_skip_rows_value or 0)

    @property
    def skip_columns(self) -> tuple[str, ...]:
        edit = getattr(self, "skip_columns_edit", None)
        text = edit.text() if edit is not None else self._layout_skip_columns_value
        return tuple(part.strip() for part in str(text or "").split(",") if part.strip())

    @property
    def selected_column_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for canonical, combo in getattr(self, "mapping_combos", {}).items():
            value = combo.currentData()
            if value not in (None, ""):
                mapping[canonical] = str(value)
        return mapping

    @property
    def selected_crs(self) -> str | None:
        if self.crs_manual_radio.isChecked():
            value = self.crs_edit.text().strip()
            return value or None
        if self.crs_none_radio.isChecked():
            return None
        detected = str(self.inspection.get("detected_crs") or "").strip()
        return detected or None

    @property
    def selected_survey_type(self) -> MagneticSurveyType:
        if self.importing_base:
            return MagneticSurveyType.BASE_STATION
        value = str(self.survey_combo.currentData() or MagneticSurveyType.GROUND.value)
        return MagneticSurveyType(value)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self._populate_tabs()
        root.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        import_button.setText("Import Dataset")
        import_button.setDefault(True)
        import_button.setProperty("variant", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _populate_tabs(self) -> None:
        self.tabs.clear()
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_layout_mapping_tab(), "Layout & Mapping")
        self.tabs.addTab(self._build_coordinates_tab(), "Coordinates & GPS")
        self.tabs.addTab(self._build_sensor_tab(), "Sensor & Channels")
        self.tabs.addTab(self._build_preview_tab(), "Data Preview")
        self.tabs.addTab(self._build_options_tab(), "Import Settings")

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("headerCard")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        text_host = QWidget()
        text_layout = QVBoxLayout(text_host)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title = QLabel("Review detected magnetic data")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "TGPAssure has inspected the file. Review the detected information; "
            "you normally do not need to enter technical coordinate-system values manually."
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        status = QLabel("AUTO-DETECTED")
        status.setObjectName("statusPill")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setFixedHeight(24)

        layout.addWidget(text_host, 1)
        layout.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        classification = str(
            self.inspection.get("suggested_acquisition_classification") or ""
        ).strip().lower()
        if classification == "stationary" and not self.importing_base:
            notice = QFrame()
            notice.setObjectName("noticeCard")
            notice_layout = QVBoxLayout(notice)
            notice_layout.setContentsMargins(12, 9, 12, 9)
            notice_layout.setSpacing(2)
            heading = QLabel("Stationary / static acquisition detected")
            heading.setObjectName("sectionTitle")
            body = QLabel(
                "The coordinates indicate little movement. TGPAssure can still import this as the "
                "primary magnetic dataset and run time, sensor, GPS, noise and stability QC. "
                "Line, tie-line and grid checks will be skipped when they are not applicable."
            )
            body.setWordWrap(True)
            body.setObjectName("mutedLabel")
            notice_layout.addWidget(heading)
            notice_layout.addWidget(body)
            layout.addWidget(notice)

        rows = [
            ("File", self._display_path()),
            ("Format", self._first("format", "reader", default="Unknown")),
            ("Delimiter", self._first("delimiter", default="—")),
            ("Detection confidence", self._confidence_label()),
            ("Log name", self._first("log_name", default="—")),
            ("Remark", self._first("remark", default="—")),
            ("Magnetic field", self._first("magnetic_channel", default="Detected automatically")),
            ("Magnetic units", self._first("magnetic_units", default="nT")),
            ("Acquisition classification", self._classification_label()),
            ("Sensor serial", self._first("sensor_serial_number", "sensor_serial", default="—")),
            ("Logger serial", self._first("logger_serial_number", "logger_serial", default="—")),
        ]
        counts = self.inspection.get("record_counts")
        if isinstance(counts, dict):
            for key, value in counts.items():
                rows.append((str(key).replace("_", " ").title(), value))

        layout.addWidget(self._key_value_table(rows), 1)
        return page

    def _build_coordinates_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        detected_crs = self._first("detected_crs", default="Not detected")
        working = self._first("recommended_working_crs", default="Not required / not detected")

        rows = [
            ("Coordinate type", self._humanize(self._first("coordinate_type", default="Unknown"))),
            ("Detected source CRS", detected_crs),
            ("Recommended working CRS", working),
            ("GPS rate", self._format_rate(self.inspection.get("gps_rate_hz"))),
            ("GPS enabled", self._yes_no(self.inspection.get("gps_enabled"))),
            ("GPS fix type", self._first("gps_fix_type", default="—")),
            ("HDOP", self._first("gps_hdop", "gps_dop_hdop", default="—")),
            ("PDOP", self._first("gps_pdop", "gps_dop_pdop", default="—")),
            ("VDOP", self._first("gps_vdop", "gps_dop_vdop", default="—")),
        ]
        layout.addWidget(self._key_value_table(rows), 1)

        movement = self.inspection.get("movement")
        if movement:
            frame = QFrame()
            frame.setObjectName("infoCard")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)
            heading = QLabel("Movement assessment")
            heading.setObjectName("sectionTitle")
            value = QLabel(self._pretty_value(movement))
            value.setWordWrap(True)
            value.setObjectName("mutedLabel")
            frame_layout.addWidget(heading)
            frame_layout.addWidget(value)
            layout.addWidget(frame)

        explanation = QLabel(
            "Source CRS describes how coordinates are stored in the file. A working CRS may be used "
            "internally for distance, spacing and gridding. Import does not rewrite the original coordinates."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("mutedLabel")
        layout.addWidget(explanation)
        return page

    def _build_sensor_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        rows = [
            ("Sensor serial", self._first("sensor_serial_number", "sensor_serial", default="—")),
            ("Sensor mode", self._humanize(self._first("sensor_mode", default="—"))),
            ("Magnetic value name", self._first("sensor_value_name", default="magnetic field")),
            ("Magnetic unit", self._first("sensor_value_unit", "magnetic_units", default="nT")),
            ("Sensor validation", self._yes_no(self.inspection.get("sensor_validation_enabled"))),
            ("BNO / orientation", self._yes_no(self.inspection.get("bno_enabled"))),
            ("Primary magnetic channel", self._first("magnetic_channel", default="Detected automatically")),
            ("Sample magnetic range", self._value_range("total_field")),
        ]
        layout.addWidget(self._key_value_table(rows), 0)

        channels = self._collect_channels()
        channel_table = QTableWidget(0, 2)
        self._configure_table(channel_table, ["Available field / channel", "Status"])
        channel_table.setRowCount(len(channels))
        for row, channel in enumerate(channels):
            channel_table.setItem(row, 0, QTableWidgetItem(channel))
            channel_table.setItem(row, 1, QTableWidgetItem("Available"))
        if not channels:
            channel_table.setRowCount(1)
            channel_table.setItem(0, 0, QTableWidgetItem("Reader will determine channels during import"))
            channel_table.setItem(0, 1, QTableWidgetItem("Automatic"))
        layout.addWidget(channel_table, 1)
        return page

    def _build_layout_mapping_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        layout_card = QFrame()
        layout_card.setObjectName("infoCard")
        layout = QGridLayout(layout_card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(7)

        title = QLabel("File layout before import")
        title.setObjectName("sectionTitle")
        layout.addWidget(title, 0, 0, 1, 4)

        layout.addWidget(QLabel("Skip first rows:"), 1, 0)
        self.skip_rows_spin = QSpinBox()
        self.skip_rows_spin.setRange(0, 5000)
        self.skip_rows_spin.setValue(int(self._layout_skip_rows_value or 0))
        self.skip_rows_spin.setToolTip("Use this when the file has report titles, notes or units above the real header row.")
        layout.addWidget(self.skip_rows_spin, 1, 1)

        layout.addWidget(QLabel("Skip columns:"), 1, 2)
        self.skip_columns_edit = QLineEdit(self._layout_skip_columns_value)
        self.skip_columns_edit.setPlaceholderText("Example: 1, 4, Notes, unused")
        self.skip_columns_edit.setToolTip("Enter 1-based column numbers or exact header names separated by commas.")
        layout.addWidget(self.skip_columns_edit, 1, 3)

        refresh_btn = QPushButton("Refresh Preview")
        refresh_btn.setObjectName("primaryButton")
        refresh_btn.setToolTip("Re-read the file preview using the skip-row and skip-column settings above.")
        refresh_btn.clicked.connect(self._refresh_preview_with_layout)
        layout.addWidget(refresh_btn, 2, 0)

        help_text = QLabel(
            "Use skip rows/columns first, then map the important magnetic fields. Required import needs Total magnetic field. If Timestamp or Date + Time is not mapped, time-dependent QC will skip and the rest of QC can still run. Extra columns can stay unmapped."
        )
        help_text.setWordWrap(True)
        help_text.setObjectName("mutedLabel")
        layout.addWidget(help_text, 2, 1, 1, 3)
        outer.addWidget(layout_card)

        map_card = QFrame()
        map_card.setObjectName("infoCard")
        map_outer = QVBoxLayout(map_card)
        map_outer.setContentsMargins(14, 12, 14, 12)
        map_outer.setSpacing(8)
        map_title = QLabel("Column mapping")
        map_title.setObjectName("sectionTitle")
        map_outer.addWidget(map_title)

        headers = [str(header) for header in (self.inspection.get("headers") or [])]
        detected = self.inspection.get("mapping") if isinstance(self.inspection.get("mapping"), dict) else {}
        self.mapping_combos = {}

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        for row, (canonical, label, required) in enumerate(_CANONICAL_FIELDS):
            label_text = QLabel(("* " if required else "") + label)
            label_text.setObjectName("mutedLabel")
            combo = QComboBox()
            combo.addItem("— Not mapped —", "")
            for header in headers:
                combo.addItem(header, header)
            selected = str(detected.get(canonical, "") or "")
            if selected:
                index = combo.findData(selected)
                if index >= 0:
                    combo.setCurrentIndex(index)
                else:
                    combo.addItem(selected, selected)
                    combo.setCurrentIndex(combo.count() - 1)
            self.mapping_combos[canonical] = combo
            grid.addWidget(label_text, row, 0)
            grid.addWidget(combo, row, 1)

        grid.setColumnStretch(1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(grid_host)
        map_outer.addWidget(scroll, 1)
        outer.addWidget(map_card, 1)
        return page

    def _refresh_preview_with_layout(self) -> None:
        path = str(self.inspection.get("path") or "").strip()
        if not path:
            QMessageBox.information(self, "Refresh Preview", "No source path is available for this preview.")
            return
        self._layout_skip_rows_value = self.skip_rows
        self._layout_skip_columns_value = ", ".join(self.skip_columns)
        try:
            options: dict[str, Any] = {
                "skip_rows": self._layout_skip_rows_value,
                "skip_columns": self.skip_columns,
            }
            if self.importing_base:
                options.update({"role": "base", "survey_type": "base_station"})
            updated = MagneticReader().inspect(path, **options)
        except Exception as exc:
            QMessageBox.critical(self, "Magnetic Preview Error", str(exc))
            return
        updated["skip_rows"] = self._layout_skip_rows_value
        updated["skip_columns"] = self._layout_skip_columns_value
        self.inspection = dict(updated)
        self._populate_tabs()
        self.tabs.setCurrentIndex(1)

    def _build_preview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        preview_tabs = QTabWidget(page)
        preview_tabs.setDocumentMode(True)

        mapping_page = QWidget()
        mapping_layout = QVBoxLayout(mapping_page)
        mapping_layout.setContentsMargins(6, 6, 6, 6)
        mapping = self.inspection.get("mapping") if isinstance(self.inspection.get("mapping"), dict) else {}
        mapping_table = QTableWidget(0, 4)
        self._configure_table(mapping_table, ["TGPAssure field", "Source column", "Detected", "Sample range"] )
        mapping_items = sorted(mapping.items()) if mapping else []
        mapping_table.setRowCount(max(1, len(mapping_items)))
        if mapping_items:
            ranges = self.inspection.get("value_ranges") if isinstance(self.inspection.get("value_ranges"), dict) else {}
            for row, (canonical, source) in enumerate(mapping_items):
                values = [
                    str(canonical).replace("_", " ").title(),
                    str(source),
                    "Mapped",
                    str(ranges.get(canonical, "—")),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    mapping_table.setItem(row, column, item)
        else:
            mapping_table.setItem(0, 0, QTableWidgetItem("No automatic mapping was returned by the reader"))
            mapping_table.setSpan(0, 0, 1, 4)
        mapping_layout.addWidget(mapping_table, 1)
        preview_tabs.addTab(mapping_page, "Detected Mapping")

        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(6, 6, 6, 6)
        preview_rows = self.inspection.get("preview") if isinstance(self.inspection.get("preview"), list) else []
        headers = list(self.inspection.get("headers") or [])
        if not headers and preview_rows:
            headers = list(preview_rows[0].keys())
        source_table = QTableWidget(0, len(headers))
        self._configure_table(source_table, [str(header) for header in headers])
        source_table.setRowCount(len(preview_rows))
        for row_index, row in enumerate(preview_rows):
            if not isinstance(row, dict):
                continue
            for column, header in enumerate(headers):
                value = str(row.get(header, ""))
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                source_table.setItem(row_index, column, item)
        if not preview_rows:
            source_table.setRowCount(1)
            source_table.setColumnCount(max(1, len(headers)))
            if headers:
                source_table.setHorizontalHeaderLabels(headers)
            source_table.setItem(0, 0, QTableWidgetItem("No preview rows were returned by the reader"))
            source_table.setSpan(0, 0, 1, max(1, len(headers)))
        source_layout.addWidget(source_table, 1)
        preview_tabs.addTab(source_page, "Source Values")
        preview_tabs.addTab(self._build_graph_preview_tab(), "Import Graphs")

        layout.addWidget(preview_tabs, 1)
        hint = QLabel(
            "These values are read directly from the selected file during inspection. The detected mapping is the mapping that will be used during import unless an explicit reader override is supplied."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)
        return page

    def _build_graph_preview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        palette_row = QHBoxLayout()
        palette_row.addWidget(QLabel("Color Palette"))
        palette_selector = PaletteSelectorButton(DEFAULT_PALETTE, page)
        palette_row.addWidget(palette_selector)
        palette_row.addStretch(1)
        layout.addLayout(palette_row)

        plot = pg.PlotWidget(background="w")
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setLabel("bottom", "Preview row")
        plot.setLabel("left", "Detected numeric value")
        plot.setTitle("Magnetic import preview — mapped numeric channels")

        preview_rows = self.inspection.get("preview") if isinstance(self.inspection.get("preview"), list) else []
        mapping = self.inspection.get("mapping") if isinstance(self.inspection.get("mapping"), dict) else {}
        candidate_columns: list[tuple[str, str]] = []
        for canonical, source in mapping.items():
            label = str(canonical).replace("_", " ").title()
            candidate_columns.append((label, str(source)))
        if not candidate_columns and preview_rows and isinstance(preview_rows[0], dict):
            for key in list(preview_rows[0].keys())[:10]:
                candidate_columns.append((str(key), str(key)))

        plotted = 0
        curves: list[object] = []
        x_axis = np.arange(len(preview_rows), dtype=float)
        for label, source_key in candidate_columns:
            values: list[float] = []
            for row in preview_rows:
                try:
                    value = float(str(row.get(source_key, "")).replace(",", "")) if isinstance(row, dict) else np.nan
                except Exception:
                    value = np.nan
                values.append(value)
            data = np.asarray(values, dtype=float)
            finite = np.isfinite(data)
            if np.count_nonzero(finite) < 2:
                continue
            y = data.copy()
            finite_values = y[finite]
            scale = float(np.nanpercentile(np.abs(finite_values - np.nanmedian(finite_values)), 95))
            if np.isfinite(scale) and scale > 0:
                y = (y - float(np.nanmedian(finite_values))) / scale
            color = palette_hex(DEFAULT_PALETTE, plotted / 4.0 if plotted else 0.0)
            curves.append(plot.plot(x_axis[finite], y[finite], pen=pg.mkPen(color, width=2), name=label))
            plotted += 1
            if plotted >= 5:
                break
        if plotted == 0:
            plot.setTitle("No numeric preview columns available for graphing; import table is still usable")
        else:
            plot.addLegend(offset=(8, 8))

        def apply_palette(name: str) -> None:
            for index, curve in enumerate(curves):
                fraction = index / max(len(curves) - 1, 1)
                curve.setPen(pg.mkPen(palette_hex(name, fraction), width=2))

        palette_selector.currentTextChanged.connect(apply_palette)
        apply_palette(palette_selector.currentText())
        layout.addWidget(plot, 1)

        help_label = QLabel("Graphs are normalized preview curves only. They help identify spikes, dead columns and obvious mapping problems before import.")
        help_label.setObjectName("mutedLabel")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        return page

    def _build_options_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        survey_card = QFrame()
        survey_card.setObjectName("infoCard")
        survey_layout = QGridLayout(survey_card)
        survey_layout.setContentsMargins(14, 12, 14, 12)
        survey_layout.setHorizontalSpacing(12)
        survey_layout.setVerticalSpacing(8)
        title = QLabel("Survey platform")
        title.setObjectName("sectionTitle")
        self.survey_combo = QComboBox()
        for label, value in (
            ("Ground", MagneticSurveyType.GROUND.value),
            ("Drone", MagneticSurveyType.DRONE.value),
            ("Airborne", MagneticSurveyType.AIRBORNE.value),
            ("Marine", MagneticSurveyType.MARINE.value),
        ):
            self.survey_combo.addItem(label, value)
        if self.importing_base:
            self.survey_combo.clear()
            self.survey_combo.addItem("Base Station", MagneticSurveyType.BASE_STATION.value)
            self.survey_combo.setEnabled(False)
        survey_layout.addWidget(title, 0, 0)
        survey_layout.addWidget(self.survey_combo, 0, 1)
        survey_help = QLabel(
            "This controls which platform-specific QC tests are applicable. It does not change the raw measurements."
        )
        survey_help.setWordWrap(True)
        survey_help.setObjectName("mutedLabel")
        survey_layout.addWidget(survey_help, 1, 0, 1, 2)
        layout.addWidget(survey_card)

        crs_card = QFrame()
        crs_card.setObjectName("infoCard")
        crs_layout = QVBoxLayout(crs_card)
        crs_layout.setContentsMargins(14, 12, 14, 12)
        crs_layout.setSpacing(8)
        crs_title = QLabel("Coordinate system handling")
        crs_title.setObjectName("sectionTitle")
        crs_layout.addWidget(crs_title)

        detected = str(self.inspection.get("detected_crs") or "").strip()
        self.crs_detected_radio = QRadioButton(
            f"Use detected coordinate system ({detected})" if detected else "Use detected coordinate system"
        )
        self.crs_none_radio = QRadioButton(
            "Import without a CRS for now (spatial QC can be skipped until one is assigned)"
        )
        self.crs_manual_radio = QRadioButton("I know the CRS and want to enter it manually")
        self.crs_group = QButtonGroup(self)
        for radio in (self.crs_detected_radio, self.crs_none_radio, self.crs_manual_radio):
            self.crs_group.addButton(radio)
            crs_layout.addWidget(radio)

        self.crs_detected_radio.setEnabled(bool(detected))
        if detected:
            self.crs_detected_radio.setChecked(True)
        else:
            self.crs_none_radio.setChecked(True)

        manual_row = QHBoxLayout()
        manual_row.setContentsMargins(22, 0, 0, 0)
        manual_label = QLabel("Manual CRS:")
        self.crs_edit = QLineEdit(detected)
        self.crs_edit.setPlaceholderText("Example: EPSG:4326")
        self.crs_edit.setEnabled(False)
        self.crs_manual_radio.toggled.connect(self.crs_edit.setEnabled)
        manual_row.addWidget(manual_label)
        manual_row.addWidget(self.crs_edit, 1)
        crs_layout.addLayout(manual_row)

        crs_help = QLabel(
            "Most users should keep the detected option. Do not guess an EPSG code. If the CRS is unknown, "
            "continue without one; non-spatial QC can still run normally."
        )
        crs_help.setWordWrap(True)
        crs_help.setObjectName("mutedLabel")
        crs_layout.addWidget(crs_help)
        layout.addWidget(crs_card)

        missing = self.inspection.get("required_missing")
        if missing:
            missing_card = QFrame()
            missing_card.setObjectName("noticeCard")
            missing_layout = QVBoxLayout(missing_card)
            missing_layout.setContentsMargins(12, 9, 12, 9)
            missing_title = QLabel("Reader notes")
            missing_title.setObjectName("sectionTitle")
            missing_text = QLabel(self._pretty_value(missing))
            missing_text.setWordWrap(True)
            missing_text.setObjectName("mutedLabel")
            missing_layout.addWidget(missing_title)
            missing_layout.addWidget(missing_text)
            layout.addWidget(missing_card)

        layout.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)
        return page

    def _display_path(self) -> str:
        value = self.inspection.get("path")
        if not value:
            return "—"
        path = Path(str(value))
        return f"{path.name}  —  {path.parent}"

    def _classification_label(self) -> str:
        value = str(self.inspection.get("suggested_acquisition_classification") or "").strip()
        if not value:
            return "Not determined"
        return self._humanize(value)

    def _collect_channels(self) -> list[str]:
        candidates: list[str] = []
        for key in ("available_channels", "channels", "detected_channels", "gps_fields", "bno_fields"):
            value = self.inspection.get(key)
            if isinstance(value, str):
                candidates.extend(part.strip() for part in value.split(",") if part.strip())
            elif isinstance(value, (list, tuple, set)):
                candidates.extend(str(item).strip() for item in value if str(item).strip())
        primary = self.inspection.get("magnetic_channel")
        if primary:
            candidates.insert(0, str(primary))
        result: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def _key_value_table(self, rows: Iterable[tuple[str, Any]]) -> QTableWidget:
        table = QTableWidget(0, 2)
        self._configure_table(table, ["Property", "Detected value"])
        materialized = list(rows)
        table.setRowCount(len(materialized))
        for row, (key, value) in enumerate(materialized):
            key_text = str(key)
            value_text = self._pretty_value(value)
            key_item = QTableWidgetItem(key_text)
            value_item = QTableWidgetItem(value_text)
            key_item.setToolTip(key_text)
            value_item.setToolTip(value_text)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, value_item)
        table.setWordWrap(True)
        table.resizeRowsToContents()
        return table

    @staticmethod
    def _configure_table(table: QTableWidget, headers: list[str]) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(25)
        table.setWordWrap(True)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = table.horizontalHeader()
        if len(headers) >= 2:
            header.setStretchLastSection(True)
            header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
            for index in range(1, len(headers)):
                header.setSectionResizeMode(index, header.ResizeMode.Stretch)

    def _confidence_label(self) -> str:
        value = self.inspection.get("confidence")
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return "—"
        return f"{confidence * 100.0:.0f}%"

    def _value_range(self, key: str) -> str:
        ranges = self.inspection.get("value_ranges")
        if isinstance(ranges, dict):
            value = ranges.get(key)
            if value not in (None, ""):
                return str(value)
        return "—"

    def _first(self, *keys: str, default: Any = None) -> Any:
        for key in keys:
            value = self.inspection.get(key)
            if value not in (None, "", [], {}):
                return value
        return default

    @staticmethod
    def _humanize(value: Any) -> str:
        return str(value).replace("_", " ").strip().title()

    @staticmethod
    def _yes_no(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, str):
            return "Yes" if value.strip().lower() in {"yes", "true", "1", "enabled"} else "No"
        return "Yes" if bool(value) else "No"

    @staticmethod
    def _format_rate(value: Any) -> str:
        if value in (None, ""):
            return "—"
        try:
            return f"{float(value):g} Hz"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _pretty_value(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, dict):
            return ";  ".join(f"{str(k).replace('_', ' ').title()}: {v}" for k, v in value.items())
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value)
        return str(value)
