from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segy_qc.qc_profiles import THRESHOLD_LABELS
from modules.seismic.segy_qc.segy_qc_controller import SegyQcController
from modules.seismic.segy_qc.segy_qc_engine import STAGES

try:
    import qtawesome as qta
except ImportError:
    qta = None


STATUS_COLORS = {
    "pending": ("#475569", "#E2E8F0"),
    "running": ("#075985", "#E0F2FE"),
    "pass": ("#166534", "#DCFCE7"),
    "warn": ("#9A3412", "#FFEDD5"),
    "warning": ("#9A3412", "#FFEDD5"),
    "fail": ("#991B1B", "#FEE2E2"),
    "failed": ("#991B1B", "#FEE2E2"),
    "cancelled": ("#475569", "#E2E8F0"),
    "completed": ("#166534", "#DCFCE7"),
}

SEVERITY_COLORS = {
    "critical": ("#FFFFFF", "#7F1D1D"),
    "error": ("#FFFFFF", "#B91C1C"),
    "warning": ("#7C2D12", "#FFEDD5"),
    "info": ("#075985", "#E0F2FE"),
}



class _LegacyStageStatusItem(QTableWidgetItem):
    """Compatibility item for older integrations that manipulated stage status directly."""

    _COLORS = {
        "pass": QColor(0, 176, 80),
        "warn": QColor(255, 200, 0),
        "warning": QColor(255, 200, 0),
        "fail": QColor(255, 0, 0),
        "failed": QColor(255, 0, 0),
        "pending": QColor(226, 232, 240),
        "running": QColor(224, 242, 254),
        "completed": QColor(0, 176, 80),
    }

    def set_status(self, status: Any) -> None:
        value = getattr(status, "value", status)
        key = str(value).lower()
        self.setText(key.upper())
        self.setBackground(self._COLORS.get(key, self._COLORS["pending"]))
        self.setTextAlignment(Qt.AlignCenter)
        font = self.font()
        font.setBold(True)
        self.setFont(font)


class _LegacyStageSection:
    """Small compatibility adapter retained for older plugin/tests API."""

    def __init__(self) -> None:
        self.status_label = QLabel("Pending")

    def reset(self) -> None:
        self.status_label.setText("Pending")

BUTTON_ICONS = {
    "open": "fa5s.folder-open",
    "run": "fa5s.play",
    "cancel": "fa5s.stop-circle",
    "approve": "fa5s.check-circle",
    "results": "fa5s.chart-bar",
    "pdf": "fa5s.file-pdf",
    "xlsx": "fa5s.file-excel",
    "settings": "fa5s.sliders-h",
    "refresh": "fa5s.sync-alt",
    "resolve": "fa5s.check",
    "reopen": "fa5s.undo",
    "trace": "fa5s.location-arrow",
    "load": "fa5s.download",
    "assign": "fa5s.user-tag",
}


class ThresholdEditorDialog(QDialog):
    def __init__(
        self,
        profile_name: str,
        thresholds: Dict[str, float],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit QC Thresholds — {profile_name}")
        self.resize(760, 620)
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("QC Threshold Configuration")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        intro = QLabel(
            "These values are saved for the selected project and profile. "
            "The exact values used are stored with every QC run."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(len(thresholds), 2, self)
        self.table.setHorizontalHeaderLabels(["Threshold", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(1, 170)
        self._keys: List[str] = []

        for row, key in enumerate(sorted(thresholds)):
            self._keys.append(key)
            name_item = QTableWidgetItem(
                THRESHOLD_LABELS.get(key, key.replace("_", " ").title())
            )
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setData(Qt.UserRole, key)
            value_item = QTableWidgetItem(f"{float(thresholds[key]):.8g}")
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, value_item)

        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            """
            QDialog { background: #F4F7FB; color: #172033; }
            QLabel#dialogTitle { font-size: 18px; font-weight: 700; color: #0F2740; }
            QLabel#mutedLabel { color: #64748B; }
            QTableWidget {
                background: #FFFFFF;
                alternate-background-color: #F8FAFC;
                border: 1px solid #D9E2EC;
                border-radius: 8px;
                gridline-color: transparent;
            }
            QHeaderView::section {
                background: #EAF0F6;
                color: #1E293B;
                border: 0;
                border-bottom: 1px solid #D3DDE7;
                padding: 8px;
                font-weight: 700;
            }
            QDialogButtonBox QPushButton {
                min-height: 32px;
                min-width: 88px;
                border-radius: 6px;
                padding: 0 14px;
            }
            """
        )

    def _validate_and_accept(self) -> None:
        try:
            for row in range(self.table.rowCount()):
                float(self.table.item(row, 1).text())
        except (TypeError, ValueError):
            QMessageBox.warning(
                self,
                "Invalid Threshold",
                "Every threshold value must be numeric.",
            )
            return
        self.accept()

    def values(self) -> Dict[str, float]:
        return {
            self.table.item(row, 0).data(Qt.UserRole): float(
                self.table.item(row, 1).text()
            )
            for row in range(self.table.rowCount())
        }


class SegyQcView(QWidget):
    generate_report_requested = Signal(str, str)
    trace_navigation_requested = Signal(int)
    view_file_requested = Signal(str)
    compare_files_requested = Signal(str, str)
    review_targets_changed = Signal()
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    def __init__(
        self,
        controller: SegyQcController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setProperty("module_id", "segy_qc")

        self._current_run_uuid: Optional[str] = None
        self._stage_row_by_key: Dict[str, int] = {}
        self._findings: List[Dict[str, Any]] = []
        self._history: List[Dict[str, Any]] = []
        self._file_info: Dict[str, Any] = {}
        self._post_qc_file_path: Optional[Path] = None
        self._summary_cards: List[QFrame] = []
        self._last_responsive_mode = ""
        # Backward-compatible public hooks used by older plugins.
        self._stage_items: Dict[str, _LegacyStageStatusItem] = {}
        self._stage_sections: Dict[str, _LegacyStageSection] = {}

        self._build_ui()
        self._connect_signals()
        self._load_profiles()
        self.refresh_history()

    @property
    def current_run_uuid(self) -> Optional[str]:
        return self._current_run_uuid

    @property
    def current_file_path(self) -> Optional[Path]:
        path = getattr(self.controller, "file_path", None)
        return Path(path).expanduser().resolve() if path else None

    @property
    def post_qc_file_path(self) -> Optional[Path]:
        return self._post_qc_file_path

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        root.addWidget(self._build_page_header())

        shell = QFrame(self)
        shell.setObjectName("segyShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(6)

        self.main_tabs = QTabWidget(self)
        self.main_tabs.setObjectName("segyMainTabs")
        self.main_tabs.setDocumentMode(True)
        self.main_tabs.setMovable(False)
        self.main_tabs.setTabPosition(QTabWidget.North)
        self.main_tabs.setIconSize(QSize(13, 13))
        self.main_tabs.tabBar().hide()
        self.main_tabs.tabBar().setExpanding(False)
        self.main_tabs.tabBar().setUsesScrollButtons(False)
        self.main_tabs.tabBar().setElideMode(Qt.ElideRight)

        self.file_tab = self._build_file_tab()
        self.configuration_tab = self._build_configuration_tab()
        self.run_tab = self._build_run_tab()
        self.results_tab = self._build_results_tab()
        self.findings_tab = self._build_findings_tab()
        self.history_tab = self._build_history_tab()
        self.headers_tab = self._build_headers_tab()

        self.main_tabs.addTab(self.file_tab, "File")
        self.main_tabs.addTab(self.configuration_tab, "Setup")
        self.main_tabs.addTab(self.run_tab, "Run")
        self.main_tabs.addTab(self.results_tab, "Results")
        self.main_tabs.addTab(self.findings_tab, "Findings")
        self.main_tabs.addTab(self.history_tab, "History")
        self.main_tabs.addTab(self.headers_tab, "Headers")

        self.main_tabs.setTabToolTip(0, "Select and inspect a SEG-Y file")
        self.main_tabs.setTabToolTip(1, "Choose QC profile, thresholds and assignee")
        self.main_tabs.setTabToolTip(2, "Start, cancel or approve the QC run")
        self.main_tabs.setTabToolTip(3, "Review stage results and metrics")
        self.main_tabs.setTabToolTip(4, "Review and resolve QC findings")
        self.main_tabs.setTabToolTip(5, "Open previous QC runs")
        self.main_tabs.setTabToolTip(6, "Inspect textual, binary and parsed headers")

        self.setup_tab = self.run_tab
        self.tabs = self.main_tabs

        sidebar = self._build_sidebar_navigation()
        shell_layout.addWidget(sidebar, 0)

        content_frame = QFrame(self)
        content_frame.setObjectName("segyContentPanel")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.main_tabs, 1)
        shell_layout.addWidget(content_frame, 1)

        root.addWidget(shell, 1)

        self.main_tabs.currentChanged.connect(self._sync_sidebar_selection)
        self._apply_styles()
        self._set_tab_icons()
        self._sync_sidebar_selection(0)
        self._update_responsive_layout(force=True)

    def _build_page_header(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("pageHeader")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QGridLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(5)

        title_panel = QFrame(frame)
        title_panel.setObjectName("headerTitlePanel")
        title_layout = QVBoxLayout(title_panel)
        title_layout.setContentsMargins(10, 6, 10, 6)
        title_layout.setSpacing(1)
        self.page_title = QLabel("SEG-Y Quality Control")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Load, inspect, run QC, review findings, and export SEG-Y audit reports.")
        self.page_subtitle.setObjectName("pageSubtitle")
        self.page_subtitle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.page_subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_layout.addWidget(self.page_title)
        title_layout.addWidget(self.page_subtitle)
        layout.addWidget(title_panel, 0, 0, 2, 1)

        self.run_status_label = QLabel("READY")
        # Compatibility status surface; kept in sync by _set_status_badge().
        self.status_label = QLabel("Ready")
        self.status_label.hide()
        self.run_status_label.setObjectName("statusBadge")
        self.run_status_label.setAlignment(Qt.AlignCenter)
        self.run_status_label.setMinimumWidth(84)
        self.run_status_label.setMaximumHeight(25)
        layout.addWidget(self.run_status_label, 0, 1, Qt.AlignRight | Qt.AlignVCenter)

        self.progress_message = QLabel("Select a SEG-Y file")
        self.progress_message.setObjectName("progressMessage")
        self.progress_message.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.progress_message.setMinimumWidth(145)
        self.progress_message.setMaximumWidth(320)
        self.progress_message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.progress_message, 0, 2, Qt.AlignRight | Qt.AlignVCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar, 1, 1, 1, 2)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(2, 0)
        return frame

    def _build_sidebar_navigation(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("segySidebar")
        sidebar.setMinimumWidth(142)
        sidebar.setMaximumWidth(168)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(7, 8, 7, 8)
        layout.setSpacing(5)

        title = QLabel("SEGY QC")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)

        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)
        self.nav_buttons: List[QPushButton] = []

        nav_items = (
            ("File", "Load & inspect"),
            ("Setup", "Profile settings"),
            ("Run", "QC workflow"),
            ("Results", "Stage metrics"),
            ("Findings", "Issues & actions"),
            ("History", "Previous runs"),
            ("Headers", "Text / binary"),
        )
        for index, (title_text, subtitle_text) in enumerate(nav_items):
            button = QPushButton(f"{title_text}\n{subtitle_text}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, page_index=index: self.main_tabs.setCurrentIndex(page_index))
            self.nav_button_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addSpacing(4)
        hint = QLabel("Use the left menu for the main workflow. Detailed tables stay inside each page.")
        hint.setObjectName("sidebarHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return sidebar

    def _sync_sidebar_selection(self, index: int) -> None:
        buttons = getattr(self, "nav_buttons", [])
        if 0 <= index < len(buttons):
            buttons[index].setChecked(True)

    def _build_setup_tab(self) -> QWidget:
        return self._build_file_tab()

    def _build_file_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        file_subtabs = QTabWidget()
        file_subtabs.setObjectName("subTabs")
        file_subtabs.setDocumentMode(True)

        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(0, 6, 0, 0)
        source_layout.setSpacing(6)
        self.source_card = self._build_source_card()
        source_layout.addWidget(self.source_card)
        source_layout.addStretch(1)
        file_subtabs.addTab(source_page, "Input Files")

        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setContentsMargins(0, 6, 0, 0)
        info_layout.setSpacing(6)
        self.file_info_card = self._build_file_info_card()
        info_layout.addWidget(self.file_info_card, 1)
        file_subtabs.addTab(info_page, "File Information")

        layout.addWidget(file_subtabs, 1)
        return page

    def _build_configuration_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        self.profile_card = self._build_profile_card()
        layout.addWidget(self.profile_card)

        note = QFrame()
        note.setObjectName("compactInfoPanel")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(10, 8, 10, 8)
        note_layout.setSpacing(3)
        note_title = QLabel("QC configuration")
        note_title.setObjectName("sectionTitle")
        note_text = QLabel(
            "Choose a profile, optionally edit its thresholds, assign a reviewer and enable stage approval. "
            "The exact settings are stored with every run."
        )
        note_text.setObjectName("mutedLabel")
        note_text.setWordWrap(True)
        note_layout.addWidget(note_title)
        note_layout.addWidget(note_text)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_run_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        self.actions_card = self._build_actions_card()
        layout.addWidget(self.actions_card)

        status_panel = QFrame()
        status_panel.setObjectName("compactInfoPanel")
        status_layout = QGridLayout(status_panel)
        status_layout.setContentsMargins(10, 8, 10, 8)
        status_layout.setHorizontalSpacing(10)
        status_layout.setVerticalSpacing(4)
        status_layout.addWidget(QLabel("Workflow"), 0, 0)
        workflow = QLabel("Run QC → review Results → resolve Findings → export report")
        workflow.setObjectName("mutedLabel")
        workflow.setWordWrap(True)
        status_layout.addWidget(workflow, 0, 1)
        status_layout.setColumnStretch(1, 1)
        layout.addWidget(status_panel)
        layout.addStretch(1)
        return page

    def _build_source_card(self) -> QGroupBox:
        group = QGroupBox("SEG-Y Review Workflow")
        group.setObjectName("sectionCard")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 14, 10, 9)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(6)

        layout.addWidget(QLabel("Raw / pre-QC"), 0, 0)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("No raw SEG-Y file selected")
        self.open_button = QPushButton("Open Raw")
        self.open_button.setObjectName("secondaryButton")
        self._set_button_icon(self.open_button, "open")
        self.view_raw_button = QPushButton("View Raw")
        self.view_raw_button.setObjectName("outlineButton")
        layout.addWidget(self.file_path_edit, 0, 1)
        layout.addWidget(self.open_button, 0, 2)
        layout.addWidget(self.view_raw_button, 0, 3)

        layout.addWidget(QLabel("Processed / post-QC"), 1, 0)
        self.post_qc_path_edit = QLineEdit()
        self.post_qc_path_edit.setReadOnly(True)
        self.post_qc_path_edit.setPlaceholderText("Optional processed SEG-Y for re-view / comparison")
        self.select_post_qc_button = QPushButton("Select Post-QC")
        self.select_post_qc_button.setObjectName("secondaryButton")
        self.view_post_qc_button = QPushButton("View Post-QC")
        self.view_post_qc_button.setObjectName("outlineButton")
        self.compare_pre_post_button = QPushButton("Compare")
        self.compare_pre_post_button.setObjectName("outlineButton")
        self.compare_pre_post_button.setToolTip("Open raw and processed SEG-Y side-by-side with synchronized navigation")
        layout.addWidget(self.post_qc_path_edit, 1, 1)
        layout.addWidget(self.select_post_qc_button, 1, 2)
        layout.addWidget(self.view_post_qc_button, 1, 3)
        layout.addWidget(self.compare_pre_post_button, 1, 4)

        self.file_validation_label = QLabel("Waiting for raw file selection")
        self.file_validation_label.setObjectName("inlineStatus")
        self.file_validation_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.file_validation_label, 2, 0, 1, 5)
        layout.setColumnStretch(1, 1)
        self._sync_review_buttons()
        return group

    def _build_profile_card(self) -> QGroupBox:
        group = QGroupBox("QC Run Configuration")
        group.setObjectName("sectionCard")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 14, 10, 9)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(7)

        layout.addWidget(QLabel("Profile"), 0, 0)
        self.profile_combo = QComboBox()
        self.profile_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.profile_combo, 0, 1)

        self.edit_thresholds_button = QPushButton("Thresholds")
        self.edit_thresholds_button.setObjectName("outlineButton")
        self._set_button_icon(self.edit_thresholds_button, "settings")
        layout.addWidget(self.edit_thresholds_button, 0, 2)

        layout.addWidget(QLabel("Assignee"), 1, 0)
        self.assignee_edit = QLineEdit()
        self.assignee_edit.setPlaceholderText("Reviewer / QC geophysicist")
        layout.addWidget(self.assignee_edit, 1, 1, 1, 2)

        self.approval_checkbox = QCheckBox("Require approval after each stage")
        self.approval_checkbox.setToolTip(
            "Pause after each completed stage until Approve is selected."
        )
        layout.addWidget(self.approval_checkbox, 2, 1, 1, 2)
        layout.setColumnStretch(1, 1)
        return group

    def _build_actions_card(self) -> QGroupBox:
        group = QGroupBox("QC Actions")
        group.setObjectName("sectionCard")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 14, 10, 9)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(7)

        self.run_button = QPushButton("Run QC")
        self.run_button.setObjectName("successButton")
        self._set_button_icon(self.run_button, "run")

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self._set_button_icon(self.cancel_button, "cancel")

        self.approve_button = QPushButton("Approve")
        self.approve_button.setObjectName("warningButton")
        self.approve_button.setEnabled(False)
        self._set_button_icon(self.approve_button, "approve")

        self.results_button = QPushButton("Results")
        self.results_button.setObjectName("secondaryButton")
        self._set_button_icon(self.results_button, "results")

        self.pdf_button = QPushButton("PDF")
        self.pdf_button.setObjectName("pdfButton")
        self._set_button_icon(self.pdf_button, "pdf")

        self.xlsx_button = QPushButton("XLSX")
        self.xlsx_button.setObjectName("excelButton")
        self._set_button_icon(self.xlsx_button, "xlsx")

        # Reports require a completed or loaded QC run.
        self.pdf_button.setEnabled(False)
        self.xlsx_button.setEnabled(False)
        self.report_button = self.pdf_button  # legacy public alias

        buttons = (
            self.run_button,
            self.cancel_button,
            self.approve_button,
            self.results_button,
            self.pdf_button,
            self.xlsx_button,
        )
        for index, button in enumerate(buttons):
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(button, index // 3, index % 3)
        for column in range(3):
            layout.setColumnStretch(column, 1)
        return group

    def _build_file_info_card(self) -> QGroupBox:
        group = QGroupBox("File Information")
        group.setObjectName("sectionCard")
        self.file_info_layout = QGridLayout(group)
        self.file_info_layout.setContentsMargins(9, 13, 9, 8)
        self.file_info_layout.setHorizontalSpacing(6)
        self.file_info_layout.setVerticalSpacing(6)

        self.file_info_labels: Dict[str, QLabel] = {}
        self.file_info_blocks: List[QFrame] = []
        fields = (
            ("file_size", "Size"),
            ("trace_count", "Traces"),
            ("sample_count", "Samples / Trace"),
            ("sample_interval", "Sample Interval"),
            ("sample_format", "Sample Format"),
            ("revision", "Revision"),
            ("byte_order", "Byte Order"),
            ("byte_order_confidence", "Endian Evidence"),
            ("text_encoding", "Text Encoding"),
            ("trace_start", "Trace Data Start"),
            ("declared_traces", "Declared Traces"),
            ("trace_extensions", "Trace Extensions"),
            ("time_basis", "Time Basis Code"),
        )

        for key, title in fields:
            block = QFrame()
            block.setObjectName("infoTile")
            block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            box = QVBoxLayout(block)
            box.setContentsMargins(7, 5, 7, 5)
            box.setSpacing(0)
            heading = QLabel(title)
            heading.setObjectName("tileTitle")
            value = QLabel("—")
            value.setObjectName("tileValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(False)
            box.addWidget(heading)
            box.addWidget(value)
            self.file_info_labels[key] = value
            self.file_info_blocks.append(block)

        return group

    def _build_results_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(6)

        top_bar = QFrame()
        top_bar.setObjectName("tabToolbar")
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(7, 5, 7, 5)
        bar_layout.setSpacing(6)

        heading_box = QVBoxLayout()
        heading_box.setSpacing(0)
        heading = QLabel("QC Run Summary")
        heading.setObjectName("sectionTitle")
        hint = QLabel("Select a stage to inspect its detailed metrics.")
        hint.setObjectName("mutedLabel")
        heading_box.addWidget(heading)
        heading_box.addWidget(hint)
        bar_layout.addLayout(heading_box)
        bar_layout.addStretch(1)

        results_refresh = QPushButton("Refresh")
        results_refresh.setObjectName("outlineButton")
        self._set_button_icon(results_refresh, "refresh")
        results_refresh.clicked.connect(self.show_results)
        bar_layout.addWidget(results_refresh)

        self.results_pdf_button = QPushButton("PDF")
        self.results_pdf_button.setObjectName("pdfButton")
        self._set_button_icon(self.results_pdf_button, "pdf")
        self.results_pdf_button.setEnabled(False)
        self.results_pdf_button.clicked.connect(lambda: self.request_report("pdf"))
        bar_layout.addWidget(self.results_pdf_button)

        self.results_xlsx_button = QPushButton("XLSX")
        self.results_xlsx_button.setObjectName("excelButton")
        self._set_button_icon(self.results_xlsx_button, "xlsx")
        self.results_xlsx_button.setEnabled(False)
        self.results_xlsx_button.clicked.connect(lambda: self.request_report("xlsx"))
        bar_layout.addWidget(self.results_xlsx_button)
        layout.addWidget(top_bar)

        self.summary_grid_widget = QWidget()
        self.summary_grid = QGridLayout(self.summary_grid_widget)
        self.summary_grid.setContentsMargins(0, 0, 0, 0)
        self.summary_grid.setHorizontalSpacing(6)
        self.summary_grid.setVerticalSpacing(6)
        self.summary_labels: Dict[str, QLabel] = {}

        for key, title, accent in (
            ("overall", "Overall Result", "blue"),
            ("score", "QC Score", "green"),
            ("stages", "Completed Stages", "purple"),
            ("findings", "Total Findings", "orange"),
            ("unresolved", "Unresolved", "red"),
        ):
            card = QFrame()
            card.setObjectName("summaryCard")
            card.setProperty("accent", accent)
            box = QVBoxLayout(card)
            box.setContentsMargins(8, 5, 8, 5)
            box.setSpacing(0)
            heading_label = QLabel(title)
            heading_label.setObjectName("summaryTitle")
            value = QLabel("—")
            value.setObjectName("summaryValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addWidget(heading_label)
            box.addWidget(value)
            self.summary_labels[key] = value
            self._summary_cards.append(card)

        layout.addWidget(self.summary_grid_widget)

        self.results_subtabs = QTabWidget()
        self.results_subtabs.setObjectName("subTabs")
        self.results_subtabs.setDocumentMode(True)
        self.results_subtabs.addTab(self._build_stage_results_page(), "Stage Results")
        self.results_subtabs.addTab(self._build_metrics_page(), "Selected Stage Metrics")
        layout.addWidget(self.results_subtabs, 1)
        return page

    def _build_stage_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)

        self.stage_table = self._create_table(0, 7)
        self.stage_table.setHorizontalHeaderLabels(
            ["#", "QC Stage", "Status", "Score", "Findings", "Duration", "Summary"]
        )
        self.stage_table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.stage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.stage_table.setColumnWidth(1, 220)
        self.stage_table.setMinimumHeight(150)
        self.stage_table.itemSelectionChanged.connect(self._update_selected_stage_metrics)
        self.stage_table.itemDoubleClicked.connect(self._show_stage_metrics)
        layout.addWidget(self.stage_table, 1)
        return page

    def _build_metrics_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.selected_stage_title = QLabel("No stage selected")
        self.selected_stage_title.setObjectName("sectionTitle")
        layout.addWidget(self.selected_stage_title)

        self.stage_metrics_edit = QPlainTextEdit()
        self.stage_metrics_edit.setReadOnly(True)
        self.stage_metrics_edit.setPlaceholderText(
            "Select a stage from the Stage Results tab to view complete metrics."
        )
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.stage_metrics_edit.setFont(font)
        layout.addWidget(self.stage_metrics_edit, 1)
        return page

    def _build_findings_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(6)

        controls_frame = QFrame()
        controls_frame.setObjectName("tabToolbar")
        controls = QGridLayout(controls_frame)
        controls.setContentsMargins(7, 5, 7, 5)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(4)

        controls.addWidget(QLabel("Severity"), 0, 0)
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All", "Critical", "Error", "Warning", "Info"])
        controls.addWidget(self.severity_filter, 0, 1)

        self.unresolved_only = QCheckBox("Open only")
        controls.addWidget(self.unresolved_only, 0, 2)

        self.resolve_button = QPushButton("Resolve")
        self.resolve_button.setObjectName("successButton")
        self._set_button_icon(self.resolve_button, "resolve")
        controls.addWidget(self.resolve_button, 0, 3)

        self.reopen_button = QPushButton("Reopen")
        self.reopen_button.setObjectName("warningButton")
        self._set_button_icon(self.reopen_button, "reopen")
        controls.addWidget(self.reopen_button, 0, 4)

        self.navigate_button = QPushButton("Trace")
        self.navigate_button.setObjectName("secondaryButton")
        self._set_button_icon(self.navigate_button, "trace")
        controls.addWidget(self.navigate_button, 0, 5)
        controls.setColumnStretch(6, 1)
        layout.addWidget(controls_frame)

        self.findings_subtabs = QTabWidget()
        self.findings_subtabs.setObjectName("subTabs")
        self.findings_subtabs.setDocumentMode(True)
        self.findings_subtabs.tabBar().setExpanding(True)
        self.findings_subtabs.tabBar().setUsesScrollButtons(False)

        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 5, 0, 0)
        self.findings_table = self._create_table(0, 8)
        self.findings_table.setHorizontalHeaderLabels(
            ["ID", "Severity", "Stage", "Code", "Description", "Observed", "Trace", "Status"]
        )
        self.findings_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.findings_table.setColumnHidden(0, True)
        header = self.findings_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.findings_table.setColumnWidth(2, 130)
        self.findings_table.setColumnWidth(3, 95)
        self.findings_table.setColumnWidth(5, 105)
        self.findings_table.itemSelectionChanged.connect(self._update_finding_detail)
        self.findings_table.itemDoubleClicked.connect(
            lambda _item: self.findings_subtabs.setCurrentIndex(1)
        )
        table_layout.addWidget(self.findings_table)
        self.findings_subtabs.addTab(table_page, "Finding List")

        detail_frame = QWidget()
        detail_layout = QGridLayout(detail_frame)
        detail_layout.setContentsMargins(9, 7, 9, 7)
        detail_layout.setHorizontalSpacing(8)
        detail_layout.setVerticalSpacing(5)

        self.finding_detail_labels: Dict[str, QLabel] = {}
        detail_fields = (
            ("severity", "Severity"),
            ("stage", "Stage"),
            ("code", "Rule"),
            ("trace", "Trace"),
            ("observed", "Observed"),
            ("expected", "Expected"),
            ("resolved", "Status"),
        )
        for index, (key, title) in enumerate(detail_fields):
            row = index // 2
            col = (index % 2) * 2
            title_label = QLabel(f"{title}:")
            title_label.setObjectName("detailTitle")
            value_label = QLabel("—")
            value_label.setObjectName("detailValue")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            detail_layout.addWidget(title_label, row, col)
            detail_layout.addWidget(value_label, row, col + 1)
            self.finding_detail_labels[key] = value_label

        detail_layout.addWidget(QLabel("Description:"), 4, 0)
        self.finding_description = QLabel("Select a finding to view its details.")
        self.finding_description.setWordWrap(True)
        self.finding_description.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.finding_description, 4, 1, 1, 3)

        detail_layout.addWidget(QLabel("Resolution Note:"), 5, 0)
        self.finding_resolution_note = QLabel("—")
        self.finding_resolution_note.setWordWrap(True)
        self.finding_resolution_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.finding_resolution_note, 5, 1, 1, 3)
        detail_layout.setColumnStretch(1, 1)
        detail_layout.setColumnStretch(3, 1)
        detail_layout.setRowStretch(6, 1)
        self.findings_subtabs.addTab(detail_frame, "Selected Finding")

        layout.addWidget(self.findings_subtabs, 1)
        return page

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(6)

        controls_frame = QFrame()
        controls_frame.setObjectName("tabToolbar")
        controls = QGridLayout(controls_frame)
        controls.setContentsMargins(7, 5, 7, 5)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(4)

        self.current_file_history_only = QCheckBox("Current file only")
        controls.addWidget(self.current_file_history_only, 0, 0)

        self.refresh_history_button = QPushButton("Refresh")
        self.refresh_history_button.setObjectName("outlineButton")
        self._set_button_icon(self.refresh_history_button, "refresh")
        controls.addWidget(self.refresh_history_button, 0, 1)

        self.load_history_button = QPushButton("Load Selected Run")
        self.load_history_button.setObjectName("secondaryButton")
        self._set_button_icon(self.load_history_button, "load")
        controls.addWidget(self.load_history_button, 0, 2)

        self.assign_button = QPushButton("Assign Selected Run")
        self.assign_button.setObjectName("warningButton")
        self._set_button_icon(self.assign_button, "assign")
        controls.addWidget(self.assign_button, 0, 3)
        controls.setColumnStretch(4, 1)
        layout.addWidget(controls_frame)

        self.history_table = self._create_table(0, 9)
        self.history_table.setHorizontalHeaderLabels(
            [
                "Run",
                "File",
                "Profile",
                "Status",
                "Result",
                "Score",
                "Findings",
                "Started",
                "Duration",
            ]
        )
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Interactive)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        self.history_table.setColumnWidth(2, 170)
        self.history_table.setColumnWidth(7, 190)
        self.history_table.doubleClicked.connect(lambda _index: self._load_selected_history())
        layout.addWidget(self.history_table, 1)
        return page

    def _build_headers_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(7, 7, 7, 7)

        self.headers_subtabs = QTabWidget()
        self.headers_subtabs.setObjectName("subTabs")
        self.headers_subtabs.setDocumentMode(True)

        text_page = QWidget()
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 8, 0, 0)
        self.text_header_edit = QPlainTextEdit()
        self.text_header_edit.setReadOnly(True)
        self.text_header_edit.setPlaceholderText("Textual header will appear after a SEG-Y file is opened.")
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.text_header_edit.setFont(font)
        text_layout.addWidget(self.text_header_edit)
        self.headers_subtabs.addTab(text_page, "Textual Header")

        binary_page = QWidget()
        binary_layout = QVBoxLayout(binary_page)
        binary_layout.setContentsMargins(0, 8, 0, 0)
        self.binary_header_table = self._create_table(0, 2)
        self.binary_header_table.setHorizontalHeaderLabels(["Binary Header Field", "Value"])
        self.binary_header_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.binary_header_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        binary_layout.addWidget(self.binary_header_table)
        self.headers_subtabs.addTab(binary_page, "Binary Header")

        metadata_page = QWidget()
        metadata_layout = QVBoxLayout(metadata_page)
        metadata_layout.setContentsMargins(0, 8, 0, 0)
        self.raw_metadata_edit = QPlainTextEdit()
        self.raw_metadata_edit.setReadOnly(True)
        self.raw_metadata_edit.setFont(font)
        self.raw_metadata_edit.setPlaceholderText("Parsed file metadata will appear here.")
        metadata_layout.addWidget(self.raw_metadata_edit)
        self.headers_subtabs.addTab(metadata_page, "Parsed Metadata")

        layout.addWidget(self.headers_subtabs)
        return page

    def _create_table(self, rows: int, columns: int) -> QTableWidget:
        table = QTableWidget(rows, columns)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(23)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setSortingEnabled(False)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setMinimumSectionSize(56)
        table.horizontalHeader().setDefaultSectionSize(92)
        table.horizontalHeader().setFixedHeight(25)
        table.horizontalHeader().setStretchLastSection(False)
        return table

    def _set_button_icon(self, button: QPushButton, key: str) -> None:
        button.setIconSize(QSize(13, 13))
        if qta is None:
            return
        icon_name = BUTTON_ICONS.get(key)
        if not icon_name:
            return
        color_map = {
            "run": "#FFFFFF",
            "cancel": "#FFFFFF",
            "approve": "#7C2D12",
            "pdf": "#FFFFFF",
            "xlsx": "#FFFFFF",
            "resolve": "#FFFFFF",
            "reopen": "#7C2D12",
            "assign": "#7C2D12",
        }
        try:
            button.setIcon(qta.icon(icon_name, color=color_map.get(key, "#1E4E79")))
        except Exception:
            pass

    def _set_tab_icons(self) -> None:
        if qta is None:
            return
        mappings = (
            (0, "fa5s.folder-open"),
            (1, "fa5s.sliders-h"),
            (2, "fa5s.play-circle"),
            (3, "fa5s.chart-line"),
            (4, "fa5s.exclamation-triangle"),
            (5, "fa5s.history"),
            (6, "fa5s.file-alt"),
        )
        for index, icon_name in mappings:
            try:
                self.main_tabs.setTabIcon(index, qta.icon(icon_name, color="#315F86"))
            except Exception:
                pass

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            SegyQcView, QWidget#contentPage, QWidget#setupPage {
                background: #F3F6F9;
                color: #143044;
                font-family: "Segoe UI", "Poppins", sans-serif;
                font-size: 8.4pt;
            }

            QFrame#pageHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1D3148, stop:0.48 #0B6E9E, stop:1 #0787C5);
                border-radius: 9px;
            }
            QFrame#headerTitlePanel {
                background: rgba(10, 31, 52, 0.42);
                border: 1px solid rgba(255,255,255,0.16);
                border-radius: 7px;
            }
            QLabel#pageTitle {
                background: transparent;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 900;
                padding: 0px;
            }
            QLabel#pageSubtitle {
                background: transparent;
                color: #D9F4FF;
                font-size: 8.0pt;
                padding: 0px;
            }
            QLabel#progressMessage {
                background: transparent;
                color: #E4F7FF;
                font-size: 8.0pt;
                font-weight: 700;
            }
            QLabel#statusBadge {
                color: #0C4A6E;
                background: #E5F4FB;
                border: 1px solid #B7DDEC;
                border-radius: 8px;
                padding: 3px 8px;
                font-size: 8.2pt;
                font-weight: 900;
            }

            QProgressBar {
                min-height: 13px;
                max-height: 13px;
                background: rgba(255,255,255,0.24);
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                font-size: 7.8pt;
                font-weight: 900;
            }
            QProgressBar::chunk {
                background: #7DD3FC;
                border-radius: 6px;
            }

            QFrame#segyShell {
                background: transparent;
                border: 0px;
            }
            QFrame#segySidebar {
                background: #FFFFFF;
                border: 1px solid #D6E2EB;
                border-radius: 8px;
            }
            QLabel#sidebarTitle {
                color: #547084;
                font-size: 7.6pt;
                font-weight: 900;
                letter-spacing: 0.6px;
                padding: 3px 7px 2px 7px;
            }
            QLabel#sidebarHint {
                color: #6B7F8D;
                background: #F6FAFC;
                border: 1px solid #E1E9EF;
                border-radius: 6px;
                padding: 5px 6px;
                font-size: 7.5pt;
            }
            QPushButton#navButton {
                background: transparent;
                color: #1E3C52;
                border: 0px;
                border-radius: 6px;
                min-height: 34px;
                max-height: 38px;
                padding: 3px 8px;
                text-align: left;
                font-size: 8.0pt;
                font-weight: 800;
            }
            QPushButton#navButton:hover {
                background: #EFF6FA;
                color: #075C84;
            }
            QPushButton#navButton:checked {
                background: #0787C5;
                color: #FFFFFF;
            }
            QFrame#segyContentPanel {
                background: #FFFFFF;
                border: 1px solid #D5E1EA;
                border-radius: 8px;
            }

            QTabWidget#segyMainTabs::pane {
                background: transparent;
                border: 0px;
                margin: 0px;
                padding: 0px;
            }
            QTabWidget#segyMainTabs QTabBar::tab {
                min-height: 0px;
                max-height: 0px;
                width: 0px;
                padding: 0px;
                margin: 0px;
                border: 0px;
            }

            QTabWidget#subTabs::pane {
                border: 1px solid #D5E1EA;
                background: #FFFFFF;
                border-radius: 5px;
                top: -1px;
            }
            QTabWidget#subTabs QTabBar::tab {
                background: #EAF0F4;
                color: #3D5668;
                border: 1px solid #D4DFE7;
                border-bottom: 0px;
                min-height: 22px;
                padding: 4px 9px;
                margin-right: 1px;
                font-size: 8.0pt;
                font-weight: 700;
            }
            QTabWidget#subTabs QTabBar::tab:selected {
                background: #FFFFFF;
                color: #0B658F;
                font-weight: 900;
            }
            QTabWidget#subTabs QTabBar::tab:hover {
                background: #F7FAFC;
            }

            QGroupBox#sectionCard {
                background: #FFFFFF;
                border: 1px solid #D8E3EB;
                border-radius: 7px;
                margin-top: 9px;
                padding-top: 8px;
                font-size: 8.4pt;
                font-weight: 900;
                color: #17364B;
            }
            QGroupBox#sectionCard::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0px 4px;
                color: #17364B;
                background: #FFFFFF;
            }

            QFrame#compactInfoPanel, QFrame#tabToolbar, QFrame#detailPanel {
                background: #F8FAFC;
                border: 1px solid #DCE4EC;
                border-radius: 6px;
            }
            QFrame#infoTile {
                background: #F8FAFC;
                border: 1px solid #E1E8EF;
                border-radius: 6px;
            }
            QLabel#tileTitle, QLabel#summaryTitle, QLabel#detailTitle {
                color: #64748B;
                font-size: 7.6pt;
                font-weight: 700;
            }
            QLabel#tileValue {
                color: #16324A;
                font-size: 8.5pt;
                font-weight: 800;
            }
            QLabel#inlineStatus {
                color: #475569;
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 5px;
                padding: 4px 6px;
                font-size: 8.0pt;
            }

            QFrame#summaryCard {
                background: #FFFFFF;
                border: 1px solid #D8E1EA;
                border-left: 3px solid #2478B5;
                border-radius: 6px;
            }
            QFrame#summaryCard[accent="green"] { border-left-color: #24915E; }
            QFrame#summaryCard[accent="purple"] { border-left-color: #7857B6; }
            QFrame#summaryCard[accent="orange"] { border-left-color: #D97706; }
            QFrame#summaryCard[accent="red"] { border-left-color: #C2414A; }
            QLabel#summaryValue {
                color: #172033;
                font-size: 12px;
                font-weight: 900;
            }
            QLabel#sectionTitle {
                background: transparent;
                color: #17364B;
                font-size: 9.5pt;
                font-weight: 900;
            }
            QLabel#mutedLabel {
                background: transparent;
                color: #607889;
                font-size: 7.8pt;
            }
            QLabel#detailValue {
                color: #1E293B;
                font-size: 8.2pt;
                font-weight: 700;
            }

            QLineEdit, QComboBox, QPlainTextEdit {
                background: #FFFFFF;
                border: 1px solid #C9D4DF;
                border-radius: 5px;
                padding: 2px 6px;
                min-height: 22px;
                selection-background-color: #9EC6E3;
                font-size: 8.2pt;
            }
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
                border: 1px solid #3A83B8;
            }
            QLineEdit:read-only {
                background: #F8FAFC;
                color: #334155;
            }
            QComboBox::drop-down {
                border: 0px;
                width: 18px;
            }
            QCheckBox {
                spacing: 5px;
                font-size: 8.1pt;
                color: #1E3443;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
            }

            QPushButton {
                min-height: 23px;
                max-height: 26px;
                border-radius: 6px;
                padding: 1px 9px;
                font-size: 8.3pt;
                font-weight: 800;
            }
            QPushButton:disabled {
                color: #8B9AA4;
                background: #EEF2F5;
                border: 1px solid #D6DEE4;
            }
            QPushButton#successButton {
                color: #FFFFFF;
                background: #188C5A;
                border: 1px solid #147449;
            }
            QPushButton#successButton:hover { background: #167A50; }
            QPushButton#dangerButton {
                color: #FFFFFF;
                background: #C2414A;
                border: 1px solid #A8323B;
            }
            QPushButton#dangerButton:hover { background: #D04D57; }
            QPushButton#warningButton {
                color: #7C2D12;
                background: #FED7AA;
                border: 1px solid #FDBA74;
            }
            QPushButton#warningButton:hover { background: #FDBA74; }
            QPushButton#secondaryButton {
                color: #FFFFFF;
                background: #0787C5;
                border: 1px solid #0473A9;
            }
            QPushButton#secondaryButton:hover { background: #087AB0; }
            QPushButton#outlineButton {
                color: #1F557D;
                background: #FFFFFF;
                border: 1px solid #8EB2CD;
            }
            QPushButton#outlineButton:hover { background: #EEF6FB; }
            QPushButton#pdfButton {
                color: #FFFFFF;
                background: #B4232C;
                border: 1px solid #941D24;
            }
            QPushButton#pdfButton:hover { background: #C92A34; }
            QPushButton#excelButton {
                color: #FFFFFF;
                background: #217346;
                border: 1px solid #185C37;
            }
            QPushButton#excelButton:hover { background: #288A55; }

            QTableWidget {
                background: #FFFFFF;
                alternate-background-color: #F7FAFC;
                border: 1px solid #D7E2EA;
                border-radius: 5px;
                gridline-color: #E5EDF2;
                selection-background-color: #D8ECF7;
                selection-color: #102A3D;
                font-size: 8.0pt;
            }
            QTableWidget::item {
                padding: 2px 4px;
                border-bottom: 1px solid #EDF1F5;
            }
            QHeaderView::section {
                background: #E5EFF5;
                color: #24485F;
                border: 0px;
                border-right: 1px solid #D4E0E8;
                border-bottom: 1px solid #CBD9E2;
                padding: 4px 5px;
                font-size: 7.8pt;
                font-weight: 900;
            }
            QHeaderView::section:hover {
                background: #DFE8F0;
            }
            QPlainTextEdit {
                font-family: Consolas, "Courier New", monospace;
                font-size: 8.0pt;
                padding: 5px;
            }
            QScrollArea {
                border: 0px;
                background: transparent;
            }
            QSplitter::handle {
                background: #DCE4EC;
                height: 3px;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.open_button.clicked.connect(self._choose_file)
        self.view_raw_button.clicked.connect(self.view_raw_file)
        self.select_post_qc_button.clicked.connect(self.select_post_qc_file)
        self.view_post_qc_button.clicked.connect(self.view_post_qc_file)
        self.compare_pre_post_button.clicked.connect(self.compare_pre_post)
        self.run_button.clicked.connect(self.run_qc)
        self.cancel_button.clicked.connect(self.controller.cancel_current)
        self.approve_button.clicked.connect(self._approve_stage)
        self.results_button.clicked.connect(self.show_results)
        self.pdf_button.clicked.connect(lambda: self.request_report("pdf"))
        self.xlsx_button.clicked.connect(lambda: self.request_report("xlsx"))
        self.edit_thresholds_button.clicked.connect(self._edit_thresholds)

        self.severity_filter.currentIndexChanged.connect(
            lambda _index: self.refresh_findings()
        )
        self.unresolved_only.toggled.connect(
            lambda _checked: self.refresh_findings()
        )
        self.resolve_button.clicked.connect(
            lambda: self._set_selected_finding_resolution(True)
        )
        self.reopen_button.clicked.connect(
            lambda: self._set_selected_finding_resolution(False)
        )
        self.navigate_button.clicked.connect(self._navigate_to_selected_trace)

        self.refresh_history_button.clicked.connect(self.refresh_history)
        self.current_file_history_only.toggled.connect(
            lambda _checked: self.refresh_history()
        )
        self.load_history_button.clicked.connect(self._load_selected_history)
        self.assign_button.clicked.connect(self._assign_selected_run)

        self.controller.file_loaded.connect(self._on_file_loaded)
        self.controller.file_load_failed.connect(self._on_file_load_failed)
        self.controller.stages_initialized.connect(self._initialize_stages)
        self.controller.run_started.connect(self._on_run_started)
        self.controller.job_progress.connect(self._on_progress)
        self.controller.stage_started.connect(self._on_stage_started)
        self.controller.stage_completed.connect(self._on_stage_completed)
        self.controller.stage_approval_required.connect(
            self._on_stage_approval_required
        )
        self.controller.run_completed.connect(self._on_run_completed)
        self.controller.run_failed.connect(self._on_run_failed)
        self.controller.run_cancelled.connect(self._on_run_cancelled)
        self.controller.run_loaded.connect(self._on_run_loaded)
        self.controller.findings_changed.connect(lambda _: self.refresh_findings())
        self.controller.data_changed.connect(self.refresh_history)

    def _load_profiles(self) -> None:
        self.profile_combo.clear()
        for descriptor in self.controller.profile_descriptors():
            self.profile_combo.addItem(descriptor["name"], descriptor["key"])
            index = self.profile_combo.count() - 1
            self.profile_combo.setItemData(
                index,
                descriptor["description"],
                Qt.ToolTipRole,
            )

    def set_file_path(self, file_path: str | Path) -> None:
        path = Path(file_path).expanduser().resolve()
        self.activity_started.emit("Opening SEG-Y File", f"Reading headers and preparing {path.name}")
        QApplication.processEvents()
        try:
            self.activity_progress.emit(20, "Reading SEG-Y textual and binary headers")
            QApplication.processEvents()
            self.controller.set_file(path)
            self.activity_progress.emit(100, "SEG-Y file is ready for QC")
        finally:
            self.activity_finished.emit()

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SEG-Y File",
            str(
                self.controller.file_path.parent
                if self.controller.file_path
                else Path.home()
            ),
            "SEG-Y Files (*.sgy *.segy);;All Files (*.*)",
        )
        if path:
            try:
                self.set_file_path(path)
            except Exception as exc:
                QMessageBox.critical(self, "SEG-Y Open Error", str(exc))

    def select_post_qc_file(self) -> None:
        raw = self.current_file_path
        start_dir = raw.parent if raw else Path.home()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Processed / Post-QC SEG-Y",
            str(start_dir),
            "SEG-Y Files (*.sgy *.segy);;All Files (*.*)",
        )
        if not path:
            return
        candidate = Path(path).expanduser().resolve()
        if raw is not None and candidate == raw:
            QMessageBox.warning(
                self,
                "Post-QC SEG-Y",
                "The post-QC file must be different from the raw/pre-QC file for comparison.",
            )
            return
        try:
            # Validate the file structurally before presenting it as a review target.
            from modules.seismic.segy_qc.segy_reader import SegyReader

            SegyReader(candidate).file_info()
        except Exception as exc:
            QMessageBox.critical(self, "Post-QC SEG-Y", f"Unable to validate SEG-Y file:\n{exc}")
            return
        self._post_qc_file_path = candidate
        self.post_qc_path_edit.setText(str(candidate))
        self._sync_review_buttons()
        self.review_targets_changed.emit()

    def view_raw_file(self) -> None:
        path = self.current_file_path
        if path is not None:
            self.view_file_requested.emit(str(path))

    def view_post_qc_file(self) -> None:
        if self._post_qc_file_path is not None:
            self.view_file_requested.emit(str(self._post_qc_file_path))

    def compare_pre_post(self) -> None:
        raw = self.current_file_path
        post = self._post_qc_file_path
        if raw is not None and post is not None:
            self.compare_files_requested.emit(str(raw), str(post))

    def _sync_review_buttons(self) -> None:
        raw_ready = self.current_file_path is not None
        post_ready = self._post_qc_file_path is not None
        for name, enabled in (
            ("view_raw_button", raw_ready),
            ("select_post_qc_button", raw_ready),
            ("view_post_qc_button", post_ready),
            ("compare_pre_post_button", raw_ready and post_ready),
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(bool(enabled))

    @staticmethod
    def _format_bytes(value: int) -> str:
        number = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if number < 1024.0 or unit == "TB":
                return f"{number:.2f} {unit}"
            number /= 1024.0
        return f"{number:.2f} TB"

    def _on_file_loaded(self, info: Dict[str, Any]) -> None:
        self._file_info = dict(info)
        binary = info.get("binary_header", {})
        file_path = info.get("file_path", "")

        self.file_path_edit.setText(file_path)
        # A newly selected raw survey invalidates any previous raw/post pairing.
        if self._post_qc_file_path is not None:
            self._post_qc_file_path = None
            self.post_qc_path_edit.clear()
        self._sync_review_buttons()
        self.review_targets_changed.emit()
        self.file_info_labels["file_size"].setText(
            self._format_bytes(int(info.get("file_size", 0)))
        )
        self.file_info_labels["trace_count"].setText("Calculated during QC")
        self.file_info_labels["sample_count"].setText(
            f"{int(binary.get('samples_per_trace', 0)):,}"
        )
        self.file_info_labels["sample_interval"].setText(
            f"{int(binary.get('sample_interval_us', 0)):,} µs"
        )
        self.file_info_labels["sample_format"].setText(
            f"{binary.get('sample_format_code', '?')} — "
            f"{binary.get('sample_format_name', 'Unknown')}"
        )
        self.file_info_labels["revision"].setText(
            str(binary.get("revision", "Unknown"))
        )
        self.file_info_labels["byte_order"].setText(
            "Big endian" if binary.get("endian") == ">" else "Little endian"
        )
        endian_evidence = str(binary.get("byte_order_detection", "Unknown"))
        self.file_info_labels["byte_order_confidence"].setText(endian_evidence.replace("-", " ").title())
        self.file_info_labels["text_encoding"].setText(
            str(info.get("text_encoding", "Unknown"))
        )
        trace_start = int(info.get("trace_data_start", 0) or 0)
        trace_start_source = str(info.get("trace_data_start_source", "unknown")).replace("-", " ")
        self.file_info_labels["trace_start"].setText(f"{trace_start:,} B • {trace_start_source}")
        declared_traces = int(binary.get("declared_trace_count", 0) or 0)
        self.file_info_labels["declared_traces"].setText(
            f"{declared_traces:,}" if declared_traces > 0 else "Not declared"
        )
        max_extensions = int(binary.get("maximum_additional_trace_headers", 0) or 0)
        self.file_info_labels["trace_extensions"].setText(
            f"Up to {max_extensions} × 240 B" if max_extensions > 0 else "Standard 240 B header"
        )
        time_basis = int(binary.get("time_basis_code", 0) or 0)
        self.file_info_labels["time_basis"].setText(str(time_basis) if time_basis else "Not declared")

        self.text_header_edit.setPlainText(info.get("text_header", ""))
        self._populate_binary_header(binary)
        self.raw_metadata_edit.setPlainText(
            json.dumps(info, indent=2, ensure_ascii=False, default=str)
        )

        self._set_status_badge("READY", "pass")
        self.file_validation_label.setText("File header loaded successfully")
        self.file_validation_label.setStyleSheet(
            "color:#166534;background:#DCFCE7;border:1px solid #BBE8CB;"
            "border-radius:5px;padding:6px 8px;font-weight:600;"
        )
        self.progress_message.setText("File ready for QC")
        self.main_tabs.setCurrentWidget(self.run_tab)
        self.refresh_history()

    def _populate_binary_header(self, binary: Dict[str, Any]) -> None:
        rows = sorted(binary.items(), key=lambda item: str(item[0]))
        self.binary_header_table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            title = key.replace("_", " ").title()
            self.binary_header_table.setItem(row, 0, QTableWidgetItem(title))
            self.binary_header_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _on_file_load_failed(self, error: str) -> None:
        self._set_status_badge("INVALID FILE", "fail")
        self.file_validation_label.setText(error)
        self.file_validation_label.setStyleSheet(
            "color:#991B1B;background:#FEE2E2;border:1px solid #F5BFC2;"
            "border-radius:5px;padding:6px 8px;font-weight:600;"
        )
        self.progress_message.setText("Header validation failed")

    def select_repeatability_base_file(self) -> None:
        start_folder = (
            self.controller.repeatability_base_path.parent
            if self.controller.repeatability_base_path
            else (self.controller.file_path.parent if self.controller.file_path else Path.home())
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select 4D Base-Survey SEG-Y",
            str(start_folder),
            "SEG-Y Files (*.sgy *.segy);;All Files (*.*)",
        )
        if not path:
            return
        try:
            info = self.controller.set_repeatability_base_file(path)
            self.progress_message.setText(
                f"4D base survey selected: {Path(info.get('file_path', path)).name}"
            )
            QMessageBox.information(
                self,
                "4D Base Survey",
                f"Base survey selected for repeatability QC:\n{info.get('file_path', path)}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "4D Base Survey", str(exc))

    def focus_stage(self, stage_key: str) -> None:
        if not self._stage_row_by_key:
            self._initialize_stages(
                [
                    {"key": key, "name": name, "order": order}
                    for order, (key, name) in enumerate(STAGES)
                ]
            )
        row = self._stage_row_by_key.get(stage_key)
        if row is None:
            QMessageBox.warning(self, "SEG-Y QC", f"Unknown QC stage: {stage_key}")
            return
        self.main_tabs.setCurrentWidget(self.results_tab)
        self.results_subtabs.setCurrentIndex(0)
        self.stage_table.selectRow(row)
        self.stage_table.scrollToItem(self.stage_table.item(row, 1))

    def edit_thresholds(self) -> None:
        self._edit_thresholds()

    def cancel_qc(self) -> None:
        if not self.controller.cancel_current():
            QMessageBox.information(
                self,
                "SEG-Y QC",
                "No SEG-Y QC run is currently active.",
            )

    def _edit_thresholds(self) -> None:
        profile_key = self.profile_combo.currentData()
        if not profile_key:
            return
        profile = self.controller.get_effective_profile(profile_key)
        dialog = ThresholdEditorDialog(profile.name, profile.thresholds, self)
        if dialog.exec() == QDialog.Accepted:
            self.controller.save_profile_overrides(profile_key, dialog.values())
            QMessageBox.information(
                self,
                "QC Profile",
                "Profile thresholds saved for this project.",
            )

    def run_qc(self) -> None:
        if not self.controller.file_path:
            self._choose_file()
            if not self.controller.file_path:
                return
        try:
            self._reset_run_ui()
            self.controller.run_pipeline(
                profile_key=str(self.profile_combo.currentData() or "standard"),
                assigned_to=self.assignee_edit.text().strip() or None,
                require_stage_approval=self.approval_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "SEG-Y QC", str(exc))

    def _reset_run_ui(self) -> None:
        self.progress_bar.setValue(0)
        self.progress_message.setText("Preparing QC pipeline")
        self._set_status_badge("STARTING", "running")
        self.stage_table.setRowCount(0)
        self._stage_row_by_key.clear()
        self._stage_items.clear()
        self._stage_sections.clear()
        self._set_report_actions_enabled(False)
        self._findings = []
        self.findings_table.setRowCount(0)
        self.stage_metrics_edit.clear()
        self.selected_stage_title.setText("No stage selected")
        self._clear_finding_detail()
        for label in self.summary_labels.values():
            label.setText("—")

    def _initialize_stages(self, stages: List[Dict[str, Any]]) -> None:
        self.stage_table.setRowCount(len(stages))
        self._stage_row_by_key.clear()
        for row, stage in enumerate(stages):
            key = stage["key"]
            self._stage_row_by_key[key] = row
            number_item = QTableWidgetItem(str(row + 1))
            number_item.setData(Qt.UserRole, key)
            self.stage_table.setItem(row, 0, number_item)
            self.stage_table.setItem(row, 1, QTableWidgetItem(stage["name"]))
            self._set_stage_status(row, "pending")
            self.stage_table.setItem(row, 3, QTableWidgetItem("—"))
            self.stage_table.setItem(row, 4, QTableWidgetItem("0"))
            self.stage_table.setItem(row, 5, QTableWidgetItem("—"))
            self.stage_table.setItem(row, 6, QTableWidgetItem("Waiting"))

    def _on_run_started(self, run_uuid: str, job_id: int) -> None:
        self._current_run_uuid = run_uuid
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.approve_button.setEnabled(False)
        self._set_status_badge("QC RUNNING", "running")
        self.summary_labels["overall"].setText("RUNNING")
        self.main_tabs.setCurrentWidget(self.results_tab)

    def _on_progress(
        self,
        job_id: int,
        overall: float,
        stage_key: str,
        stage_progress: float,
        message: str,
    ) -> None:
        self.progress_bar.setValue(int(max(0.0, min(1.0, overall)) * 1000))
        self.progress_message.setText(message)
        row = self._stage_row_by_key.get(stage_key)
        if row is not None:
            item = self.stage_table.item(row, 6)
            if item is not None:
                item.setText(f"{message} ({stage_progress * 100:.0f}%)")

    def _on_stage_started(self, stage_key: str, stage_name: str, order: int) -> None:
        row = self._stage_row_by_key.get(stage_key)
        if row is not None:
            self._set_stage_status(row, "running")
            self.stage_table.selectRow(row)
            self.results_subtabs.setCurrentIndex(0)

    def _on_stage_completed(
        self,
        stage_key: str,
        status: str,
        metrics: Dict[str, Any],
        findings: List[Dict[str, Any]],
    ) -> None:
        row = self._stage_row_by_key.get(stage_key)
        if row is None:
            return

        self._set_stage_status(row, status)
        score = metrics.get("overall_score_before_summary")
        if score is None:
            run_stages = self.controller.get_stage_results(self._current_run_uuid)
            stage = next(
                (
                    item
                    for item in run_stages
                    if item.get("stage_key") == stage_key
                ),
                None,
            )
            score = stage.get("score") if stage else None
            duration = stage.get("duration_ms") if stage else None
            message = stage.get("message") if stage else ""
        else:
            duration = None
            message = ""

        self.stage_table.item(row, 3).setText(
            "—" if score is None else f"{float(score):.1f}"
        )
        self.stage_table.item(row, 4).setText(str(len(findings)))
        if duration is not None:
            self.stage_table.item(row, 5).setText(f"{int(duration):,} ms")
        self.stage_table.item(row, 6).setText(
            message or self._metrics_preview(metrics)
        )
        self.stage_table.item(row, 0).setData(Qt.UserRole + 1, metrics)
        self.refresh_findings()

    @staticmethod
    def _metrics_preview(metrics: Dict[str, Any]) -> str:
        if not metrics:
            return "Completed"
        parts: List[str] = []
        for key, value in metrics.items():
            if isinstance(value, (str, int, float, bool)) and key != "text":
                parts.append(f"{key.replace('_', ' ')}: {value}")
            if len(parts) == 2:
                break
        return "; ".join(parts) or "Completed"

    def _set_stage_status(self, row: int, status: str) -> None:
        foreground, background = STATUS_COLORS.get(
            status.lower(),
            STATUS_COLORS["pending"],
        )
        item = self.stage_table.item(row, 2) or QTableWidgetItem()
        item.setText(status.upper())
        item.setForeground(QColor(foreground))
        item.setBackground(QColor(background))
        item.setTextAlignment(Qt.AlignCenter)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.stage_table.setItem(row, 2, item)

    def _set_status_badge(self, text: str, status: str) -> None:
        foreground, background = STATUS_COLORS.get(
            status.lower(),
            STATUS_COLORS["pending"],
        )
        self.run_status_label.setText(text)
        self.status_label.setText(text.replace("QC ", "").replace("LOADED: ", "").title())
        self.run_status_label.setStyleSheet(
            f"color:{foreground};background:{background};"
            "border:1px solid rgba(100,116,139,0.25);"
            "border-radius:10px;padding:4px 10px;font-weight:700;"
        )

    def _on_stage_approval_required(self, stage_key: str, stage_name: str) -> None:
        self.approve_button.setEnabled(True)
        self.approve_button.setProperty("stage_key", stage_key)
        self.progress_message.setText(f"Awaiting approval after {stage_name}")
        self._set_status_badge("APPROVAL REQUIRED", "warn")
        self.main_tabs.setCurrentWidget(self.setup_tab)

    def _approve_stage(self) -> None:
        stage_key = self.approve_button.property("stage_key")
        self.controller.approve_stage(str(stage_key) if stage_key else None)
        self.approve_button.setEnabled(False)
        self._set_status_badge("QC RUNNING", "running")
        self.main_tabs.setCurrentWidget(self.results_tab)

    def _on_run_completed(self, run_uuid: str, summary: Dict[str, Any]) -> None:
        self._current_run_uuid = run_uuid
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.approve_button.setEnabled(False)
        self._set_report_actions_enabled(True)
        self.progress_bar.setValue(1000)

        result = str(summary.get("overall_result", "completed"))
        self._set_status_badge(f"QC {result.upper()}", result)
        self.progress_message.setText(
            f"Completed in {int(summary.get('duration_ms', 0)) / 1000.0:.2f} s"
        )
        self.file_info_labels["trace_count"].setText(
            f"{int(summary.get('trace_count', 0)):,}"
        )
        self._update_summary(summary)
        self.refresh_findings()
        self.refresh_history()
        self.main_tabs.setCurrentWidget(self.results_tab)
        self.results_subtabs.setCurrentIndex(0)

    def _on_run_failed(self, run_uuid: str, error: str) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.approve_button.setEnabled(False)
        self._set_status_badge("QC FAILED", "fail")
        self.progress_message.setText(error)
        QMessageBox.critical(self, "SEG-Y QC Failed", error)
        self.refresh_history()

    def _on_run_cancelled(self, run_uuid: str) -> None:
        if self._current_run_uuid != run_uuid:
            return
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.approve_button.setEnabled(False)
        self._set_status_badge("QC CANCELLED", "cancelled")
        self.progress_message.setText("Run cancelled by user")
        self.refresh_history()

    def _on_run_loaded(
        self,
        run_uuid: str,
        run: Dict[str, Any],
        stages: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
    ) -> None:
        self._current_run_uuid = run_uuid
        summary = run.get("summary") or {}
        source_path = (
            run.get("source_file_path")
            or run.get("file_absolute_path")
            or ""
        )
        self.file_path_edit.setText(source_path)

        self._initialize_stages(
            [
                {
                    "key": stage["stage_key"],
                    "name": stage["stage_name"],
                    "order": stage["stage_order"],
                }
                for stage in stages
            ]
        )

        for stage in stages:
            row = self._stage_row_by_key.get(stage["stage_key"])
            if row is None:
                continue
            self._set_stage_status(
                row,
                str(stage.get("result") or stage.get("status") or "pending"),
            )
            self.stage_table.item(row, 3).setText(
                "—"
                if stage.get("score") is None
                else f"{float(stage['score']):.1f}"
            )
            self.stage_table.item(row, 4).setText(
                str(stage.get("finding_count", 0))
            )
            duration = stage.get("duration_ms")
            self.stage_table.item(row, 5).setText(
                "—" if duration is None else f"{int(duration):,} ms"
            )
            self.stage_table.item(row, 6).setText(
                stage.get("message")
                or self._metrics_preview(stage.get("metrics", {}))
            )
            self.stage_table.item(row, 0).setData(
                Qt.UserRole + 1,
                stage.get("metrics", {}),
            )

        self._findings = findings
        self._populate_findings(findings)
        self._update_summary(summary or run)

        loaded_result = str(run.get("overall_result", "pending"))
        self._set_report_actions_enabled(True)
        self._set_status_badge(f"LOADED: {loaded_result.upper()}", loaded_result)
        self.main_tabs.setCurrentWidget(self.results_tab)
        self.results_subtabs.setCurrentIndex(0)

    def _update_summary(self, summary: Dict[str, Any]) -> None:
        result = str(
            summary.get("overall_result", summary.get("result", "—"))
        ).upper()
        self.summary_labels["overall"].setText(result)
        self.summary_labels["score"].setText(
            f"{float(summary.get('score') or 0):.1f}"
        )
        self.summary_labels["stages"].setText(
            str(summary.get("stage_count", self.stage_table.rowCount()))
        )
        finding_count = int(summary.get("finding_count", len(self._findings)))
        self.summary_labels["findings"].setText(str(finding_count))
        unresolved = sum(not bool(item.get("is_resolved")) for item in self._findings)
        self.summary_labels["unresolved"].setText(str(unresolved))

        foreground, background = STATUS_COLORS.get(
            result.lower(),
            STATUS_COLORS["pending"],
        )
        self.summary_labels["overall"].setStyleSheet(
            f"color:{foreground};background:{background};"
            "border-radius:5px;padding:2px 6px;font-size:18px;font-weight:700;"
        )

    def show_results(self) -> None:
        if not self._current_run_uuid:
            runs = self.controller.list_runs(
                limit=1,
                current_file_only=bool(self.controller.file_path),
            )
            if not runs:
                QMessageBox.information(
                    self,
                    "SEG-Y QC Results",
                    "No QC result is available yet.",
                )
                return
            self.controller.load_run(runs[0]["run_uuid"])
        else:
            self.controller.load_run(self._current_run_uuid)
        self.main_tabs.setCurrentWidget(self.results_tab)

    def refresh_findings(self) -> None:
        if not self._current_run_uuid:
            self._populate_findings([])
            return

        severity = self.severity_filter.currentText().lower()
        severity_value = None if severity == "all" else severity
        resolved = False if self.unresolved_only.isChecked() else None
        self._findings = self.controller.get_findings(
            self._current_run_uuid,
            severity=severity_value,
            resolved=resolved,
        )
        self._populate_findings(self._findings)

        all_findings = self.controller.get_findings(self._current_run_uuid)
        self.summary_labels["findings"].setText(str(len(all_findings)))
        self.summary_labels["unresolved"].setText(
            str(sum(not bool(item.get("is_resolved")) for item in all_findings))
        )

    def _populate_findings(self, findings: List[Dict[str, Any]]) -> None:
        self.findings_table.setRowCount(len(findings))
        for row, finding in enumerate(findings):
            severity = str(finding.get("severity", "info")).lower()
            trace_value = finding.get("trace_index") or self._context_trace(
                finding.get("context", {})
            )
            values = (
                finding.get("id"),
                severity.upper(),
                finding.get("stage_name") or finding.get("stage_key") or "",
                finding.get("finding_code") or finding.get("code") or "",
                finding.get("description") or "",
                self._observed_text(finding),
                trace_value,
                "RESOLVED" if finding.get("is_resolved") else "OPEN",
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                if column == 0:
                    item.setData(Qt.UserRole, int(finding.get("id", 0)))
                if column == 1:
                    foreground, background = SEVERITY_COLORS.get(
                        severity,
                        ("#334155", "#F1F5F9"),
                    )
                    item.setForeground(QColor(foreground))
                    item.setBackground(QColor(background))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 7:
                    resolved = bool(finding.get("is_resolved"))
                    item.setForeground(QColor("#166534" if resolved else "#9A3412"))
                    item.setBackground(QColor("#DCFCE7" if resolved else "#FFEDD5"))
                    item.setTextAlignment(Qt.AlignCenter)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                item.setData(Qt.UserRole + 1, finding)
                self.findings_table.setItem(row, column, item)

        if findings:
            self.findings_table.selectRow(0)
        else:
            self._clear_finding_detail()

    @staticmethod
    def _context_trace(context: Dict[str, Any]) -> str:
        traces = context.get("affected_trace_indices", []) if isinstance(context, dict) else []
        if not traces:
            return ""
        return ", ".join(str(value) for value in traces[:5]) + (
            "…" if len(traces) > 5 else ""
        )

    @staticmethod
    def _observed_text(finding: Dict[str, Any]) -> str:
        value = finding.get("observed_value")
        unit = finding.get("unit") or ""
        return "" if value is None else f"{float(value):.5g} {unit}".strip()

    @staticmethod
    def _expected_text(finding: Dict[str, Any]) -> str:
        minimum = finding.get("expected_min")
        maximum = finding.get("expected_max")
        unit = finding.get("unit") or ""
        if minimum is not None and maximum is not None:
            return f"{float(minimum):.5g}–{float(maximum):.5g} {unit}".strip()
        if minimum is not None:
            return f"≥ {float(minimum):.5g} {unit}".strip()
        if maximum is not None:
            return f"≤ {float(maximum):.5g} {unit}".strip()
        return ""

    def _selected_finding_id(self) -> Optional[int]:
        row = self.findings_table.currentRow()
        if row < 0:
            return None
        item = self.findings_table.item(row, 0)
        if item is None:
            return None
        return int(item.data(Qt.UserRole))

    def _selected_finding(self) -> Optional[Dict[str, Any]]:
        row = self.findings_table.currentRow()
        if row < 0:
            return None
        item = self.findings_table.item(row, 0)
        if item is None:
            return None
        data = item.data(Qt.UserRole + 1)
        return data if isinstance(data, dict) else None

    def _update_finding_detail(self) -> None:
        finding = self._selected_finding()
        if not finding:
            self._clear_finding_detail()
            return

        trace = finding.get("trace_index") or self._context_trace(
            finding.get("context", {})
        )
        self.finding_detail_labels["severity"].setText(
            str(finding.get("severity", "info")).upper()
        )
        self.finding_detail_labels["stage"].setText(
            str(finding.get("stage_name") or finding.get("stage_key") or "—")
        )
        self.finding_detail_labels["code"].setText(
            str(finding.get("finding_code") or finding.get("code") or "—")
        )
        self.finding_detail_labels["trace"].setText(str(trace or "—"))
        self.finding_detail_labels["observed"].setText(
            self._observed_text(finding) or "—"
        )
        self.finding_detail_labels["expected"].setText(
            self._expected_text(finding) or "—"
        )
        self.finding_detail_labels["resolved"].setText(
            "Resolved" if finding.get("is_resolved") else "Open"
        )
        self.finding_description.setText(
            str(finding.get("description") or "—")
        )
        self.finding_resolution_note.setText(
            str(finding.get("resolution_note") or "—")
        )

    def _clear_finding_detail(self) -> None:
        if not hasattr(self, "finding_detail_labels"):
            return
        for label in self.finding_detail_labels.values():
            label.setText("—")
        self.finding_description.setText("Select a finding to view its details.")
        self.finding_resolution_note.setText("—")

    def _set_selected_finding_resolution(self, resolved: bool) -> None:
        finding_id = self._selected_finding_id()
        if not finding_id:
            QMessageBox.information(self, "QC Finding", "Select a finding first.")
            return

        note = ""
        if resolved:
            note, ok = QInputDialog.getMultiLineText(
                self,
                "Resolve QC Finding",
                "Resolution note:",
            )
            if not ok or not note.strip():
                return

        self.controller.set_finding_resolution(finding_id, resolved, note)
        self.refresh_findings()

    def _navigate_to_selected_trace(self) -> None:
        finding = self._selected_finding()
        if not finding:
            return

        trace_value = finding.get("trace_index")
        if trace_value is None:
            context = finding.get("context", {})
            traces = (
                context.get("affected_trace_indices", [])
                if isinstance(context, dict)
                else []
            )
            trace_value = traces[0] if traces else None

        try:
            trace_index = int(trace_value)
        except (TypeError, ValueError):
            QMessageBox.information(
                self,
                "Trace Navigation",
                "This finding does not contain a trace reference.",
            )
            return
        self.trace_navigation_requested.emit(trace_index)

    def refresh_history(self) -> None:
        self._history = self.controller.list_runs(
            limit=200,
            current_file_only=(
                self.current_file_history_only.isChecked()
                if hasattr(self, "current_file_history_only")
                else False
            ),
        )
        self.history_table.setRowCount(len(self._history))

        for row, run in enumerate(self._history):
            summary = run.get("summary") or {}
            duration_ms = run.get("duration_ms") or summary.get("duration_ms") or 0
            values = (
                str(run.get("run_uuid", ""))[:8],
                run.get("source_file_name") or run.get("file_display_name") or "",
                run.get("qc_profile") or "",
                run.get("status") or "",
                run.get("overall_result") or "",
                "—" if run.get("score") is None else f"{float(run['score']):.1f}",
                summary.get("finding_count", "—"),
                run.get("started_at") or run.get("created_at") or "",
                f"{int(duration_ms) / 1000.0:.2f} s",
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, run.get("run_uuid"))
                if column in (3, 4):
                    foreground, background = STATUS_COLORS.get(
                        str(value).lower(),
                        STATUS_COLORS["pending"],
                    )
                    item.setForeground(QColor(foreground))
                    item.setBackground(QColor(background))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.history_table.setItem(row, column, item)

    def _selected_history_uuid(self) -> Optional[str]:
        row = self.history_table.currentRow()
        if row < 0:
            return None
        item = self.history_table.item(row, 0)
        return item.data(Qt.UserRole) if item is not None else None

    def _load_selected_history(self) -> None:
        run_uuid = self._selected_history_uuid()
        if not run_uuid:
            QMessageBox.information(self, "QC History", "Select a QC run first.")
            return
        try:
            self.controller.load_run(run_uuid)
        except Exception as exc:
            QMessageBox.critical(self, "QC History", str(exc))

    def _assign_selected_run(self) -> None:
        run_uuid = self._selected_history_uuid()
        if not run_uuid:
            QMessageBox.information(
                self,
                "QC Assignment",
                "Select a QC run first.",
            )
            return

        assignee, ok = QInputDialog.getText(
            self,
            "Assign QC Run",
            "Assignee:",
        )
        if ok and assignee.strip():
            self.controller.assign_run(run_uuid, assignee.strip())
            self.refresh_history()

    def _set_report_actions_enabled(self, enabled: bool) -> None:
        for name in (
            "pdf_button",
            "xlsx_button",
            "results_pdf_button",
            "results_xlsx_button",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(bool(enabled))

    def set_stages(self, stages: List[Any]) -> None:
        """Compatibility API for older integrations while using the current stage table."""
        normalized: List[Dict[str, Any]] = []
        for order, stage in enumerate(stages):
            if isinstance(stage, dict):
                key = str(stage.get("key") or stage.get("stage_key") or f"stage{order + 1}")
                name = str(stage.get("name") or stage.get("stage_name") or key)
            else:
                key = str(stage)
                name = key.replace("_", " ").title()
            normalized.append({"key": key, "name": name, "order": order})

        self._initialize_stages(normalized)
        self._stage_items.clear()
        self._stage_sections.clear()
        for stage in normalized:
            key = stage["key"]
            row = self._stage_row_by_key[key]
            item = _LegacyStageStatusItem("PENDING")
            item.set_status("pending")
            self.stage_table.setItem(row, 2, item)
            self._stage_items[key] = item
            self._stage_sections[key] = _LegacyStageSection()

    def reset_view(self) -> None:
        """Reset transient run state without discarding the selected source/profile."""
        self._current_run_uuid = None
        self.progress_bar.setValue(0)
        self.progress_message.setText("Ready")
        self._set_status_badge("READY", "pending")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.approve_button.setEnabled(False)
        self._set_report_actions_enabled(False)
        for item in self._stage_items.values():
            item.set_status("pending")
        for section in self._stage_sections.values():
            section.reset()
        for row in range(self.stage_table.rowCount()):
            if self.stage_table.item(row, 2) not in self._stage_items.values():
                self._set_stage_status(row, "pending")

    def request_report(self, format_type: str) -> None:
        if not self._current_run_uuid:
            QMessageBox.information(
                self,
                "SEG-Y QC Report",
                "Select or complete a QC run first.",
            )
            return
        self.generate_report_requested.emit(
            self._current_run_uuid,
            format_type.lower(),
        )

    def _update_selected_stage_metrics(self) -> None:
        row = self.stage_table.currentRow()
        if row < 0:
            return
        name_item = self.stage_table.item(row, 1)
        key_item = self.stage_table.item(row, 0)
        if name_item is None or key_item is None:
            return
        metrics = key_item.data(Qt.UserRole + 1) or {}
        self.selected_stage_title.setText(name_item.text())
        self.stage_metrics_edit.setPlainText(
            json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
        )

    def _show_stage_metrics(self, item: QTableWidgetItem) -> None:
        row = item.row()
        key_item = self.stage_table.item(row, 0)
        name_item = self.stage_table.item(row, 1)
        if key_item is None or name_item is None:
            return
        metrics = key_item.data(Qt.UserRole + 1) or {}
        stage_name = name_item.text()

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{stage_name} Metrics")
        dialog.resize(760, 560)
        dialog.setMinimumSize(520, 360)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel(stage_name)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
        )
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        text.setFont(font)
        layout.addWidget(text)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _update_responsive_layout(self, force: bool = False) -> None:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        if width < 720:
            mode = "compact"
        elif width < 1050:
            mode = "medium"
        else:
            mode = "wide"

        state = f"{mode}:{'short' if height < 610 else 'normal'}"
        if not force and state == self._last_responsive_mode:
            return
        self._last_responsive_mode = state

        self.page_subtitle.setVisible(width >= 760 and height >= 520)
        self.progress_message.setVisible(width >= 720)
        self._reflow_file_info(mode)
        self._reflow_summary_cards(mode)
        self._reflow_toolbar_controls(mode)

        self.main_tabs.tabBar().setExpanding(True)
        self.main_tabs.tabBar().setUsesScrollButtons(False)
        self.main_tabs.tabBar().setElideMode(Qt.ElideRight)

        compact_rows = 21 if height < 610 else 23
        for table in (
            self.stage_table,
            self.findings_table,
            self.history_table,
            self.binary_header_table,
        ):
            table.verticalHeader().setDefaultSectionSize(compact_rows)

    def _clear_layout_positions(self, layout: QGridLayout, widgets: List[QWidget]) -> None:
        for widget in widgets:
            layout.removeWidget(widget)

    def _reflow_setup_cards(self, mode: str) -> None:
        return

    def _reflow_file_info(self, mode: str) -> None:
        for block in self.file_info_blocks:
            self.file_info_layout.removeWidget(block)

        columns = 4 if mode in ("wide", "medium") else 2
        for index, block in enumerate(self.file_info_blocks):
            row = index // columns
            column = index % columns
            self.file_info_layout.addWidget(block, row, column)

        for column in range(4):
            self.file_info_layout.setColumnStretch(column, 1 if column < columns else 0)

    def _reflow_summary_cards(self, mode: str) -> None:
        for card in self._summary_cards:
            self.summary_grid.removeWidget(card)

        columns = 5 if mode in ("wide", "medium") else 3
        for index, card in enumerate(self._summary_cards):
            row = index // columns
            column = index % columns
            self.summary_grid.addWidget(card, row, column)

        for column in range(5):
            self.summary_grid.setColumnStretch(column, 1 if column < columns else 0)

    def _reflow_toolbar_controls(self, mode: str) -> None:
        compact = mode == "compact"
        button_texts = {
            self.resolve_button: ("Resolve", "Resolve"),
            self.reopen_button: ("Reopen", "Reopen"),
            self.navigate_button: ("Trace", "Trace"),
            self.load_history_button: ("Load Selected Run", "Load"),
            self.assign_button: ("Assign Selected Run", "Assign"),
        }
        for button, (normal, small) in button_texts.items():
            button.setText(small if compact else normal)
            button.setIconSize(QSize(12, 12))

        self.main_tabs.tabBar().setUsesScrollButtons(False)
        self.main_tabs.tabBar().setElideMode(Qt.ElideRight)

