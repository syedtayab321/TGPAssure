from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.domain.data_quality_service import DataQualityService
from ui.icons import get_icon


class _MetricCard(QFrame):
    def __init__(self, title: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dqMetricCard")
        self.setProperty("accent", accent)
        self.setMinimumWidth(88)
        self.setFixedHeight(54)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("dqMetricTitle")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("dqMetricValue")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)


class DataQualityDashboard(QWidget):
    def __init__(self, data_quality_service: DataQualityService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._svc = data_quality_service
        self._last_layout_mode = ""
        self.setObjectName("dataQualityDashboard")
        self.setProperty("module_id", "segy_qc")
        self.setMinimumSize(430, 260)
        self._build_ui()
        self._apply_style()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 5, 6, 6)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(1, 0, 1, 0)
        header.setSpacing(6)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(0)
        self.title_label = QLabel("Data Quality Dashboard")
        self.title_label.setObjectName("dqTitle")
        self.subtitle_label = QLabel("SEG-Y QC overview, stages and run history")
        self.subtitle_label.setObjectName("dqSubtitle")
        title_block.addWidget(self.title_label)
        title_block.addWidget(self.subtitle_label)
        header.addLayout(title_block, 1)

        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("dqRefreshButton")
        self.refresh_button.setText("Refresh")
        self.refresh_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.refresh_button.setIcon(get_icon("view-refresh", size=13))
        self.refresh_button.setIconSize(QSize(13, 13))
        self.refresh_button.setFixedHeight(25)
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("dqTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setUsesScrollButtons(False)
        root.addWidget(self.tabs, 1)

        self.overview_tab = QWidget()
        self.stages_tab = QWidget()
        self.runs_tab = QWidget()
        self.tabs.addTab(self.overview_tab, get_icon("view-dashboard", size=12), "Overview")
        self.tabs.addTab(self.stages_tab, get_icon("view-statistics", size=12), "Stages")
        self.tabs.addTab(self.runs_tab, get_icon("view-list-details", size=12), "Runs")

        self._build_overview_tab()
        self._build_stages_tab()
        self._build_runs_tab()

    def _build_overview_tab(self) -> None:
        layout = QVBoxLayout(self.overview_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.cards_host = QWidget()
        self.cards_grid = QGridLayout(self.cards_host)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setHorizontalSpacing(5)
        self.cards_grid.setVerticalSpacing(5)
        layout.addWidget(self.cards_host, 0)

        card_definitions = (
            ("total_runs", "QC Runs", "#2F6FA5"),
            ("passed_runs", "Passed", "#25835B"),
            ("warning_runs", "Warnings", "#C77A18"),
            ("failed_runs", "Failed", "#B84343"),
            ("average_score", "Avg. Score", "#6E57A5"),
            ("unresolved_findings", "Unresolved", "#A8525B"),
        )
        self.cards: Dict[str, _MetricCard] = {}
        for key, title, accent in card_definitions:
            card = _MetricCard(title, accent, self.cards_host)
            self.cards[key] = card

        self.overview_panels = QWidget()
        self.overview_grid = QGridLayout(self.overview_panels)
        self.overview_grid.setContentsMargins(0, 0, 0, 0)
        self.overview_grid.setHorizontalSpacing(5)
        self.overview_grid.setVerticalSpacing(5)
        layout.addWidget(self.overview_panels, 1)

        self.severity_panel = QFrame()
        self.severity_panel.setObjectName("dqPanel")
        severity_layout = QVBoxLayout(self.severity_panel)
        severity_layout.setContentsMargins(8, 6, 8, 6)
        severity_layout.setSpacing(3)
        severity_title = QLabel("Findings by severity")
        severity_title.setObjectName("dqPanelTitle")
        severity_layout.addWidget(severity_title)

        self.severity_bars: Dict[str, QProgressBar] = {}
        self.severity_counts: Dict[str, QLabel] = {}
        severity_colors = {
            "critical": "#7F1D1D",
            "error": "#C2413B",
            "warning": "#D08A24",
            "info": "#287FA8",
        }
        for severity in ("critical", "error", "warning", "info"):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(5)
            label = QLabel(severity.title())
            label.setObjectName("dqSeverityLabel")
            label.setFixedWidth(48)
            bar = QProgressBar()
            bar.setObjectName("dqSeverityBar")
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            bar.setStyleSheet(
                "QProgressBar{background:#E9EEF3;border:0;border-radius:3px;}"
                f"QProgressBar::chunk{{background:{severity_colors[severity]};border-radius:3px;}}"
            )
            count = QLabel("0")
            count.setObjectName("dqSeverityCount")
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            count.setFixedWidth(26)
            row.addWidget(label)
            row.addWidget(bar, 1)
            row.addWidget(count)
            severity_layout.addLayout(row)
            self.severity_bars[severity] = bar
            self.severity_counts[severity] = count
        severity_layout.addStretch(1)

        self.latest_panel = QFrame()
        self.latest_panel.setObjectName("dqPanel")
        latest_layout = QVBoxLayout(self.latest_panel)
        latest_layout.setContentsMargins(8, 6, 8, 6)
        latest_layout.setSpacing(3)
        latest_header = QHBoxLayout()
        latest_header.setContentsMargins(0, 0, 0, 0)
        latest_header.setSpacing(5)
        latest_title = QLabel("Latest QC run")
        latest_title.setObjectName("dqPanelTitle")
        self.latest_status = QLabel("NO RUN")
        self.latest_status.setObjectName("dqStatusBadge")
        self.latest_status.setAlignment(Qt.AlignCenter)
        latest_header.addWidget(latest_title)
        latest_header.addStretch(1)
        latest_header.addWidget(self.latest_status)
        latest_layout.addLayout(latest_header)

        self.latest_file = QLabel("No QC runs available")
        self.latest_file.setObjectName("dqLatestFile")
        self.latest_file.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.latest_file.setWordWrap(False)
        latest_layout.addWidget(self.latest_file)

        self.latest_details = QLabel("Profile: —    Score: —    Created: —")
        self.latest_details.setObjectName("dqLatestDetails")
        self.latest_details.setWordWrap(True)
        latest_layout.addWidget(self.latest_details)

        self.latest_progress = QProgressBar()
        self.latest_progress.setObjectName("dqScoreBar")
        self.latest_progress.setRange(0, 100)
        self.latest_progress.setValue(0)
        self.latest_progress.setFormat("Score %v")
        self.latest_progress.setFixedHeight(14)
        latest_layout.addWidget(self.latest_progress)
        latest_layout.addStretch(1)

        self._relayout_overview(force=True)

    def _build_stages_tab(self) -> None:
        layout = QVBoxLayout(self.stages_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(1, 0, 1, 0)
        toolbar.setSpacing(5)
        label = QLabel("Latest run stage results")
        label.setObjectName("dqSectionLabel")
        toolbar.addWidget(label)
        toolbar.addStretch(1)
        self.stage_count_label = QLabel("0 stages")
        self.stage_count_label.setObjectName("dqMutedLabel")
        toolbar.addWidget(self.stage_count_label)
        layout.addLayout(toolbar)

        self.stage_table = QTableWidget(0, 4)
        self.stage_table.setObjectName("dqTable")
        self.stage_table.setHorizontalHeaderLabels(["Stage", "Result", "Score", "Duration"])
        self._configure_table(self.stage_table)
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            self.stage_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.stage_table, 1)

    def _build_runs_tab(self) -> None:
        layout = QVBoxLayout(self.runs_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(1, 0, 1, 0)
        toolbar.setSpacing(5)
        label = QLabel("Recent QC runs")
        label.setObjectName("dqSectionLabel")
        toolbar.addWidget(label)
        toolbar.addStretch(1)
        self.run_count_label = QLabel("0 runs")
        self.run_count_label.setObjectName("dqMutedLabel")
        toolbar.addWidget(self.run_count_label)
        layout.addLayout(toolbar)

        self.runs_table = QTableWidget(0, 7)
        self.runs_table.setObjectName("dqTable")
        self.runs_table.setHorizontalHeaderLabels(
            ["Run", "File", "Profile", "Status", "Result", "Score", "Created"]
        )
        self._configure_table(self.runs_table)
        self.runs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.runs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for column in range(2, 7):
            self.runs_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.runs_table, 1)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(21)
        table.horizontalHeader().setMinimumSectionSize(42)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setSortingEnabled(False)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#dataQualityDashboard {
                background: #F2F5F8;
                color: #263746;
                font-family: Poppins, Segoe UI, Arial;
                font-size: 9px;
            }
            QLabel#dqTitle {
                color: #173A5E;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#dqSubtitle, QLabel#dqMutedLabel {
                color: #718096;
                font-size: 8px;
            }
            QToolButton#dqRefreshButton {
                background: #2F6FA5;
                color: white;
                border: 1px solid #285F8D;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 8px;
                font-weight: 600;
            }
            QToolButton#dqRefreshButton:hover { background: #3A7FB8; }
            QToolButton#dqRefreshButton:pressed { background: #245A87; }
            QTabWidget#dqTabs::pane {
                background: #FFFFFF;
                border: 1px solid #C9D3DD;
                border-radius: 4px;
                top: -1px;
            }
            QTabWidget#dqTabs QTabBar::tab {
                min-height: 23px;
                padding: 2px 10px;
                margin-right: 1px;
                color: #516579;
                background: #E8EDF2;
                border: 1px solid #C9D3DD;
                border-bottom: 0;
                font-size: 8px;
                font-weight: 600;
            }
            QTabWidget#dqTabs QTabBar::tab:selected {
                color: #173A5E;
                background: #FFFFFF;
                border-top: 2px solid #2F6FA5;
            }
            QTabWidget#dqTabs QTabBar::tab:hover:!selected {
                background: #F2F6F9;
            }
            QFrame#dqMetricCard, QFrame#dqPanel {
                background: #FFFFFF;
                border: 1px solid #D4DDE5;
                border-radius: 4px;
            }
            QLabel#dqMetricTitle {
                color: #6A7C8E;
                font-size: 7px;
                font-weight: 600;
                border: 0;
            }
            QLabel#dqMetricValue {
                color: #173A5E;
                font-size: 15px;
                font-weight: 700;
                border: 0;
            }
            QLabel#dqPanelTitle, QLabel#dqSectionLabel {
                color: #294A68;
                font-size: 9px;
                font-weight: 700;
                border: 0;
            }
            QLabel#dqSeverityLabel, QLabel#dqSeverityCount {
                color: #526779;
                font-size: 8px;
                border: 0;
            }
            QLabel#dqSeverityCount { font-weight: 700; }
            QLabel#dqLatestFile {
                color: #243E55;
                font-size: 9px;
                font-weight: 700;
                border: 0;
            }
            QLabel#dqLatestDetails {
                color: #607386;
                font-size: 8px;
                border: 0;
            }
            QLabel#dqStatusBadge {
                color: #FFFFFF;
                background: #718096;
                border-radius: 7px;
                padding: 1px 7px;
                min-height: 13px;
                font-size: 7px;
                font-weight: 700;
            }
            QProgressBar#dqScoreBar {
                color: #43586B;
                background: #E7EDF2;
                border: 0;
                border-radius: 3px;
                text-align: center;
                font-size: 7px;
            }
            QProgressBar#dqScoreBar::chunk {
                background: #2F83B8;
                border-radius: 3px;
            }
            QTableWidget#dqTable {
                background: #FFFFFF;
                alternate-background-color: #F6F8FA;
                border: 1px solid #D1DAE2;
                border-radius: 3px;
                color: #30485D;
                font-size: 8px;
                selection-background-color: #DCEAF5;
                selection-color: #173A5E;
            }
            QTableWidget#dqTable::item {
                padding: 1px 4px;
                border: 0;
            }
            QTableWidget#dqTable QHeaderView::section {
                background: #E9EEF3;
                color: #415A70;
                border: 0;
                border-right: 1px solid #D0D9E1;
                border-bottom: 1px solid #C7D2DC;
                padding: 3px 5px;
                min-height: 20px;
                font-size: 8px;
                font-weight: 700;
            }
            QScrollBar:vertical {
                background: #EEF2F5;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #AAB8C5;
                border-radius: 3px;
                min-height: 22px;
            }
            QScrollBar:horizontal {
                background: #EEF2F5;
                height: 8px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #AAB8C5;
                border-radius: 3px;
                min-width: 22px;
            }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            """
        )

    def _relayout_cards(self) -> None:
        width = max(1, self.overview_tab.width())
        columns = 6 if width >= 900 else 3 if width >= 570 else 2
        mode = f"cards-{columns}"
        if mode == self._last_layout_mode:
            return
        self._last_layout_mode = mode
        while self.cards_grid.count():
            self.cards_grid.takeAt(0)
        for index, card in enumerate(self.cards.values()):
            self.cards_grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self.cards_grid.setColumnStretch(column, 1)

    def _relayout_overview(self, force: bool = False) -> None:
        width = max(1, self.overview_tab.width())
        horizontal = width >= 650
        target_mode = "horizontal" if horizontal else "vertical"
        if not force and getattr(self, "_overview_mode", "") == target_mode:
            return
        self._overview_mode = target_mode
        self.overview_grid.removeWidget(self.severity_panel)
        self.overview_grid.removeWidget(self.latest_panel)
        if horizontal:
            self.overview_grid.addWidget(self.severity_panel, 0, 0)
            self.overview_grid.addWidget(self.latest_panel, 0, 1)
            self.overview_grid.setColumnStretch(0, 1)
            self.overview_grid.setColumnStretch(1, 2)
            self.overview_grid.setRowStretch(0, 1)
        else:
            self.overview_grid.addWidget(self.latest_panel, 0, 0)
            self.overview_grid.addWidget(self.severity_panel, 1, 0)
            self.overview_grid.setColumnStretch(0, 1)
            self.overview_grid.setRowStretch(0, 1)
            self.overview_grid.setRowStretch(1, 1)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.subtitle_label.setVisible(self.width() >= 620)
        self.refresh_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon if self.width() >= 520 else Qt.ToolButtonIconOnly
        )
        self._relayout_cards()
        self._relayout_overview()

    def show_overview(self) -> None:
        self.tabs.setCurrentWidget(self.overview_tab)
        self.refresh()

    def refresh(self) -> None:
        try:
            summary = self._svc.latest_qc_summary()
            for key, card in self.cards.items():
                value = summary.get(key, 0)
                if key == "average_score":
                    card.value_label.setText(f"{float(value):.1f}")
                else:
                    card.value_label.setText(str(int(value or 0)))

            counts = self._svc.count_findings_by_severity()
            maximum = max(1, max(counts.values(), default=0))
            for severity, bar in self.severity_bars.items():
                count = int(counts.get(severity, 0) or 0)
                bar.setValue(round(100 * count / maximum))
                self.severity_counts[severity].setText(str(count))

            latest = summary.get("latest")
            if latest:
                result = str(latest.get("overall_result") or latest.get("status") or "pending").lower()
                file_name = latest.get("source_file_name") or "Unknown file"
                profile = latest.get("qc_profile") or "Unknown"
                created = str(latest.get("created_at") or "—")
                score = latest.get("score")
                score_text = "—" if score is None else f"{float(score):.1f}"
                score_value = 0 if score is None else max(0, min(100, round(float(score))))

                self.latest_file.setText(str(file_name))
                self.latest_file.setToolTip(str(file_name))
                self.latest_details.setText(
                    f"Profile: {profile}    Score: {score_text}    Created: {created}"
                )
                self.latest_progress.setValue(score_value)
                self._set_status_badge(result)
            else:
                self.latest_file.setText("No QC runs available")
                self.latest_details.setText("Profile: —    Score: —    Created: —")
                self.latest_progress.setValue(0)
                self._set_status_badge("no run")

            stages = self._svc.latest_stage_scores()
            self.stage_table.setRowCount(len(stages))
            self.stage_count_label.setText(f"{len(stages)} stage{'s' if len(stages) != 1 else ''}")
            for row, stage in enumerate(stages):
                values = (
                    stage.get("stage_name", ""),
                    str(stage.get("result") or "").upper(),
                    "—" if stage.get("score") is None else f"{float(stage['score']):.1f}",
                    "—" if stage.get("duration_ms") is None else f"{int(stage['duration_ms']):,} ms",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 1:
                        self._color_state_item(item, str(value))
                    if column in (1, 2, 3):
                        item.setTextAlignment(Qt.AlignCenter)
                    self.stage_table.setItem(row, column, item)

            runs = self._svc.recent_runs(100)
            self.runs_table.setRowCount(len(runs))
            self.run_count_label.setText(f"{len(runs)} run{'s' if len(runs) != 1 else ''}")
            for row, run in enumerate(runs):
                values = (
                    str(run.get("run_uuid", ""))[:8],
                    run.get("source_file_name") or "",
                    run.get("qc_profile") or "",
                    str(run.get("status") or "").upper(),
                    str(run.get("overall_result") or "").upper(),
                    "—" if run.get("score") is None else f"{float(run['score']):.1f}",
                    run.get("created_at") or "",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column in (3, 4):
                        self._color_state_item(item, str(value))
                    if column in (0, 3, 4, 5):
                        item.setTextAlignment(Qt.AlignCenter)
                    self.runs_table.setItem(row, column, item)
        except Exception as exc:
            self.latest_file.setText("Dashboard unavailable")
            self.latest_details.setText(str(exc))
            self._set_status_badge("error")

    def _set_status_badge(self, state: str) -> None:
        normalized = state.lower().strip()
        colors = {
            "pass": "#25835B",
            "passed": "#25835B",
            "completed": "#25835B",
            "warn": "#C77A18",
            "warning": "#C77A18",
            "fail": "#B84343",
            "failed": "#B84343",
            "error": "#B84343",
            "cancelled": "#6F7782",
            "running": "#2F6FA5",
            "pending": "#718096",
            "no run": "#718096",
        }
        self.latest_status.setText(normalized.upper() or "UNKNOWN")
        self.latest_status.setStyleSheet(
            "color:#FFFFFF;border:0;border-radius:7px;padding:1px 7px;"
            f"background:{colors.get(normalized, '#718096')};font-size:7px;font-weight:700;"
        )

    @staticmethod
    def _color_state_item(item: QTableWidgetItem, state: str) -> None:
        normalized = state.lower().strip()
        if normalized in {"pass", "passed", "completed"}:
            item.setForeground(QColor("#167044"))
        elif normalized in {"warn", "warning"}:
            item.setForeground(QColor("#B96E12"))
        elif normalized in {"fail", "failed", "error"}:
            item.setForeground(QColor("#B3262E"))
        elif normalized in {"cancelled"}:
            item.setForeground(QColor("#6B7280"))
        else:
            item.setForeground(QColor("#2F6FA5"))
