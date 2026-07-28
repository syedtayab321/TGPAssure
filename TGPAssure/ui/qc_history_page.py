from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_access.db_engine import DatabaseEngine
from core.data_access.qc_history_repository import QcHistoryRepository
from core.data_access.local_file_cache import LocalActivityHistory


class QcHistoryPage(QWidget):
    """Unified browser for completed and historical QC runs across modules."""

    file_open_requested = Signal(str)
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    def __init__(self, db_engine: DatabaseEngine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "home")
        self.repository = QcHistoryRepository(db_engine)
        self.local_history = LocalActivityHistory()
        self._runs: list[dict[str, Any]] = []
        self._activities: list[dict[str, Any]] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("QC Run History")
        title.setStyleSheet("font-size:18px;font-weight:700;")
        subtitle = QLabel("All persisted QC runs, source files, stage results, findings, scores, and run details")
        subtitle.setStyleSheet("color:#607080;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch(1)
        self.details_button = QPushButton("View Details")
        self.details_button.clicked.connect(self._open_selected_details_dialog)
        title_row.addWidget(self.details_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(refresh_button)
        root.addLayout(title_row)

        controls = QFrame(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search file, profile, path, or run ID…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filters)
        self.module_combo = QComboBox()
        self.module_combo.addItem("All Modules", "all")
        self.module_combo.addItem("SEG-Y", "segy")
        self.module_combo.addItem("SEG-D", "segd")
        self.module_combo.addItem("Magnetic", "magnetic")
        self.module_combo.addItem("Gravity", "gravity")
        self.module_combo.addItem("Electrical", "electrical")
        self.module_combo.addItem("Geodetic", "geodetic")
        self.module_combo.addItem("Vibroseis", "vibroseis")
        self.module_combo.currentIndexChanged.connect(self._apply_filters)
        controls_layout.addWidget(QLabel("Find:"))
        controls_layout.addWidget(self.search_edit, 1)
        controls_layout.addWidget(QLabel("Module:"))
        controls_layout.addWidget(self.module_combo)
        root.addWidget(controls)

        metrics = QFrame(self)
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(8)
        self.total_card = self._metric_card("Runs", "0")
        self.pass_card = self._metric_card("Pass", "0")
        self.warn_card = self._metric_card("Review / Warn", "0")
        self.fail_card = self._metric_card("Fail", "0")
        self.finding_card = self._metric_card("Findings", "0")
        for card in (self.total_card, self.pass_card, self.warn_card, self.fail_card, self.finding_card):
            metrics_layout.addWidget(card, 1)
        root.addWidget(metrics)

        splitter = QSplitter(Qt.Vertical, self)
        self.run_table = QTableWidget(0, 10, splitter)
        self.run_table.setHorizontalHeaderLabels(
            ["Date", "File", "Module", "Profile", "Status", "Result", "Score", "Stages", "Findings", "Duration"]
        )
        self.run_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.run_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.run_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.run_table.setAlternatingRowColors(True)
        self.run_table.setSortingEnabled(False)
        self._configure_compact_table(
            self.run_table,
            widths={0: 132, 2: 72, 3: 128, 4: 68, 5: 68, 6: 54, 7: 52, 8: 88, 9: 72},
            stretch_columns=(1,),
        )
        self.run_table.setMinimumHeight(210)
        self.run_table.itemSelectionChanged.connect(self._show_selected_run)
        self.run_table.itemDoubleClicked.connect(self._open_selected_file)
        splitter.addWidget(self.run_table)

        detail_tabs = QTabWidget(splitter)
        detail_tabs.setDocumentMode(True)
        detail_tabs.addTab(self._build_overview_tab(), "Overview")
        detail_tabs.addTab(self._build_stages_tab(), "Stages")
        detail_tabs.addTab(self._build_findings_tab(), "Findings")
        detail_tabs.addTab(self._build_activity_tab(), "Activity Log")
        splitter.addWidget(detail_tabs)
        splitter.setSizes([370, 310])
        root.addWidget(splitter, 1)

    def _metric_card(self, caption: str, value: str) -> QFrame:
        card = QFrame(self)
        card.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 7)
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        value_label.setStyleSheet("font-size:18px;font-weight:700;")
        caption_label = QLabel(caption)
        caption_label.setStyleSheet("color:#667788;font-size:10px;")
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        card.value_label = value_label  # type: ignore[attr-defined]
        return card

    def _build_overview_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        overview = QGroupBox("Selected QC Run")
        grid = QGridLayout(overview)
        self.overview_labels: dict[str, QLabel] = {}
        fields = [
            ("file", "File"),
            ("path", "Path"),
            ("module", "Module"),
            ("profile", "Profile"),
            ("result", "Result"),
            ("score", "Score"),
            ("started", "Started"),
            ("completed", "Completed"),
            ("duration", "Duration"),
            ("run_uuid", "Run ID"),
        ]
        for index, (key, caption) in enumerate(fields):
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(key in {"file", "path", "run_uuid"})
            self.overview_labels[key] = label
            grid.addWidget(QLabel(f"{caption}:"), index, 0, Qt.AlignTop)
            grid.addWidget(label, index, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(overview)
        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        summary_font = QFont(self.summary_text.font())
        summary_font.setPointSizeF(8.5)
        self.summary_text.setFont(summary_font)
        self.summary_text.setPlaceholderText("Run summary and parameters will appear here.")
        layout.addWidget(self.summary_text, 1)
        open_button = QPushButton("Open Source File")
        open_button.clicked.connect(self._open_selected_file)
        layout.addWidget(open_button, 0, Qt.AlignRight)
        return page

    def _build_stages_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        self.stage_table = QTableWidget(0, 7, page)
        self.stage_table.setHorizontalHeaderLabels(["#", "Stage", "Status", "Result", "Score", "Duration", "Message / Metrics"])
        self.stage_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stage_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._configure_compact_table(
            self.stage_table,
            widths={0: 36, 1: 142, 2: 72, 3: 68, 4: 58, 5: 76},
            stretch_columns=(6,),
        )
        layout.addWidget(self.stage_table)
        return page

    def _build_findings_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        self.finding_table = QTableWidget(0, 7, page)
        self.finding_table.setHorizontalHeaderLabels(["Severity", "Stage", "Code", "Title", "Description", "Action", "Resolved"])
        self.finding_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.finding_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._configure_compact_table(
            self.finding_table,
            widths={0: 72, 1: 112, 2: 105, 3: 170, 5: 185, 6: 66},
            stretch_columns=(4,),
        )
        layout.addWidget(self.finding_table)
        return page

    def _build_activity_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        self.activity_table = QTableWidget(0, 7, page)
        self.activity_table.setHorizontalHeaderLabels(["Time", "Module", "Action", "Status", "File", "Path", "Details"])
        self.activity_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.activity_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.activity_table.itemDoubleClicked.connect(lambda _item: self._open_selected_details_dialog())
        self._configure_compact_table(
            self.activity_table,
            widths={0: 132, 1: 76, 2: 118, 3: 70, 4: 190, 5: 210},
            stretch_columns=(6,),
        )
        layout.addWidget(self.activity_table)
        return page

    @staticmethod
    def _configure_compact_table(
        table: QTableWidget,
        *,
        widths: dict[int, int],
        stretch_columns: tuple[int, ...] = (),
    ) -> None:
        """Apply a dense, predictable table layout without content-driven overflow."""
        font = QFont(table.font())
        font.setPointSizeF(8.5)
        table.setFont(font)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideRight)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setShowGrid(False)
        table.setStyleSheet(
            "QTableWidget{font-size:8.5pt;gridline-color:#E5E9ED;}"
            "QTableWidget::item{padding:2px 4px;border-bottom:1px solid #EEF1F3;}"
            "QHeaderView::section{font-size:8.5pt;font-weight:600;padding:4px 5px;}"
        )
        vertical = table.verticalHeader()
        vertical.setVisible(False)
        vertical.setDefaultSectionSize(24)
        vertical.setMinimumSectionSize(22)

        header = table.horizontalHeader()
        header.setMinimumSectionSize(42)
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        for column, width in widths.items():
            if 0 <= column < table.columnCount():
                table.setColumnWidth(column, width)
        for column in stretch_columns:
            if 0 <= column < table.columnCount():
                header.setSectionResizeMode(column, QHeaderView.Stretch)

    def refresh(self) -> None:
        self.activity_started.emit("Refreshing QC History", "Reading saved QC runs from the project database")
        try:
            self.activity_progress.emit(25, "Loading recent QC runs")
            self._runs = self.repository.list_runs(limit=2000)
            self.activity_progress.emit(45, "Loading local file-open and action history")
            self._activities = self.local_history.list(limit=2000)
            self.activity_progress.emit(65, "Applying filters and rebuilding compact result tables")
            self._apply_filters()
            self.activity_progress.emit(100, "QC history is ready")
        finally:
            self.activity_finished.emit()

    def _apply_filters(self, *_args) -> None:
        token = self.search_edit.text().strip().lower()
        module = str(self.module_combo.currentData() or "all").lower()
        filtered: list[dict[str, Any]] = []
        for run in self._runs:
            if module != "all" and str(run.get("module") or "").lower() != module:
                continue
            haystack = " ".join(
                str(run.get(key) or "")
                for key in ("display_file", "file_path", "qc_profile", "run_uuid", "module", "overall_result")
            ).lower()
            if token and token not in haystack:
                continue
            filtered.append(run)
        self._populate_runs(filtered)

        activities: list[dict[str, Any]] = []
        for item in self._activities:
            if module != "all" and str(item.get("module") or "").lower() != module:
                continue
            haystack = " ".join(str(item.get(key) or "") for key in ("file_name", "file_path", "module", "action", "status"))
            haystack += " " + json.dumps(item.get("details") or {}, ensure_ascii=False, default=str)
            if token and token not in haystack.lower():
                continue
            activities.append(item)
        self._populate_activity(activities)

    def _populate_runs(self, runs: list[dict[str, Any]]) -> None:
        self.run_table.setUpdatesEnabled(False)
        try:
            self.run_table.setRowCount(len(runs))
            for row_index, run in enumerate(runs):
                values = [
                    self._display_date(run.get("completed_at") or run.get("started_at") or run.get("created_at")),
                    str(run.get("display_file") or "Unknown"),
                    self._module_label(run.get("module")),
                    str(run.get("qc_profile") or "—"),
                    str(run.get("status") or "—").title(),
                    str(run.get("overall_result") or "—").title(),
                    self._score(run.get("score")),
                    str(run.get("stage_count") or 0),
                    f"{int(run.get('finding_count') or 0)} ({int(run.get('unresolved_count') or 0)} open)",
                    self._duration(run.get("duration_ms")),
                ]
                for column, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    if column == 0:
                        item.setData(Qt.UserRole, run.get("run_uuid"))
                    if column in {4, 5}:
                        self._color_status_item(item, text)
                    self.run_table.setItem(row_index, column, item)
        finally:
            self.run_table.setUpdatesEnabled(True)
        self._update_metrics(runs)
        if runs:
            self.run_table.selectRow(0)
        else:
            self._clear_details()

    def _update_metrics(self, runs: list[dict[str, Any]]) -> None:
        results = [str(run.get("overall_result") or run.get("status") or "").lower() for run in runs]
        pass_count = sum(value in {"pass", "passed", "success", "completed"} for value in results)
        fail_count = sum(value in {"fail", "failed", "error", "critical"} for value in results)
        warn_count = sum(value in {"warn", "warning", "review", "partial"} for value in results)
        findings = sum(int(run.get("finding_count") or 0) for run in runs)
        self.total_card.value_label.setText(str(len(runs)))  # type: ignore[attr-defined]
        self.pass_card.value_label.setText(str(pass_count))  # type: ignore[attr-defined]
        self.warn_card.value_label.setText(str(warn_count))  # type: ignore[attr-defined]
        self.fail_card.value_label.setText(str(fail_count))  # type: ignore[attr-defined]
        self.finding_card.value_label.setText(str(findings))  # type: ignore[attr-defined]

    def _populate_activity(self, activities: list[dict[str, Any]]) -> None:
        if not hasattr(self, "activity_table"):
            return
        self.activity_table.setRowCount(len(activities))
        for row, item in enumerate(activities):
            details = item.get("details") or {}
            values = [
                self._display_date(item.get("timestamp")),
                self._module_label(item.get("module")),
                str(item.get("action") or "—").replace("_", " ").title(),
                str(item.get("status") or "—").title(),
                str(item.get("file_name") or "—"),
                str(item.get("file_path") or "—"),
                json.dumps(details, ensure_ascii=False, default=str),
            ]
            for column, text in enumerate(values):
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                if column == 0:
                    cell.setData(Qt.UserRole, item)
                if column == 3:
                    self._color_status_item(cell, text)
                self.activity_table.setItem(row, column, cell)

    def _selected_activity(self) -> dict[str, Any] | None:
        if not hasattr(self, "activity_table"):
            return None
        row = self.activity_table.currentRow()
        if row < 0:
            return None
        item = self.activity_table.item(row, 0)
        data = item.data(Qt.UserRole) if item is not None else None
        return data if isinstance(data, dict) else None

    def _open_selected_details_dialog(self) -> None:
        run_uuid = self._selected_run_uuid()
        details = self.repository.get_run_details(run_uuid) if run_uuid else None
        activity = self._selected_activity()
        dialog = QDialog(self)
        dialog.setWindowTitle("TGPAssure History Details")
        dialog.resize(900, 560)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget(dialog)
        layout.addWidget(tabs, 1)

        def text_page(title: str, payload: Any) -> None:
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            tabs.addTab(editor, title)

        if details:
            text_page("Run Summary", {k: details.get(k) for k in ("run_uuid", "display_file", "file_path", "module", "qc_profile", "status", "overall_result", "score", "started_at", "completed_at", "duration_ms", "summary", "parameters")})
            text_page("Stages", details.get("stages") or [])
            text_page("Findings", details.get("findings") or [])
        if activity:
            text_page("Selected Activity", activity)
        if not details and not activity:
            text_page("Details", {"message": "Select a QC run or activity row first."})
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _selected_run_uuid(self) -> str:
        row = self.run_table.currentRow()
        if row < 0:
            return ""
        item = self.run_table.item(row, 0)
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _show_selected_run(self) -> None:
        run_uuid = self._selected_run_uuid()
        if not run_uuid:
            self._clear_details()
            return
        details = self.repository.get_run_details(run_uuid)
        if details is None:
            self._clear_details()
            return
        self._populate_overview(details)
        self._populate_stages(details.get("stages") or [])
        self._populate_findings(details.get("findings") or [])

    def _populate_overview(self, run: dict[str, Any]) -> None:
        self.overview_labels["file"].setText(str(run.get("display_file") or "—"))
        self.overview_labels["path"].setText(str(run.get("file_path") or "—"))
        self.overview_labels["module"].setText(self._module_label(run.get("module")))
        profile = str(run.get("qc_profile") or "—")
        if run.get("profile_version"):
            profile += f"  v{run['profile_version']}"
        self.overview_labels["profile"].setText(profile)
        self.overview_labels["result"].setText(str(run.get("overall_result") or run.get("status") or "—").title())
        self.overview_labels["score"].setText(self._score(run.get("score")))
        self.overview_labels["started"].setText(self._display_date(run.get("started_at")))
        self.overview_labels["completed"].setText(self._display_date(run.get("completed_at")))
        self.overview_labels["duration"].setText(self._duration(run.get("duration_ms")))
        self.overview_labels["run_uuid"].setText(str(run.get("run_uuid") or "—"))
        payload = {
            "summary": run.get("summary") or {},
            "parameters": run.get("parameters") or {},
        }
        self.summary_text.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False, default=str))

    def _populate_stages(self, stages: list[dict[str, Any]]) -> None:
        self.stage_table.setRowCount(len(stages))
        for row, stage in enumerate(stages):
            metrics = stage.get("metrics") or {}
            message = str(stage.get("message") or "")
            if metrics:
                metric_text = json.dumps(metrics, ensure_ascii=False, default=str)
                message = f"{message} | {metric_text}" if message else metric_text
            values = [
                str(stage.get("stage_order") or row + 1),
                str(stage.get("stage_name") or stage.get("stage_key") or "—"),
                str(stage.get("status") or "—").title(),
                str(stage.get("result") or "—").title(),
                self._score(stage.get("score")),
                self._duration(stage.get("duration_ms")),
                message or "—",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column in {2, 3}:
                    self._color_status_item(item, text)
                self.stage_table.setItem(row, column, item)

    def _populate_findings(self, findings: list[dict[str, Any]]) -> None:
        self.finding_table.setRowCount(len(findings))
        for row, finding in enumerate(findings):
            context = finding.get("context") or {}
            action = finding.get("suggested_action") or context.get("suggested_action") or "—"
            values = [
                str(finding.get("severity") or "—").title(),
                str(finding.get("stage_name") or finding.get("stage_key") or "—"),
                str(finding.get("finding_code") or "—"),
                str(finding.get("title") or "—"),
                str(finding.get("description") or "—"),
                str(action),
                "Yes" if bool(finding.get("is_resolved")) else "No",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == 0:
                    self._color_status_item(item, text)
                self.finding_table.setItem(row, column, item)

    def _open_selected_file(self, *_args) -> None:
        run_uuid = self._selected_run_uuid()
        if not run_uuid:
            return
        details = self.repository.get_run_details(run_uuid)
        path = str((details or {}).get("file_path") or "")
        if path and Path(path).exists():
            self.file_open_requested.emit(path)

    def _clear_details(self) -> None:
        for label in getattr(self, "overview_labels", {}).values():
            label.setText("—")
        if hasattr(self, "summary_text"):
            self.summary_text.clear()
        if hasattr(self, "stage_table"):
            self.stage_table.setRowCount(0)
        if hasattr(self, "finding_table"):
            self.finding_table.setRowCount(0)

    @staticmethod
    def _display_date(value: Any) -> str:
        text = str(value or "")
        if not text:
            return "—"
        return text.replace("T", " ").replace("+00:00", " UTC")[:23]

    @staticmethod
    def _module_label(value: Any) -> str:
        mapping = {"segy": "SEG-Y", "segd": "SEG-D", "magnetic": "Magnetic", "gravity": "Gravity", "electrical": "Electrical", "geodetic": "Geodetic", "vibroseis": "Vibroseis"}
        text = str(value or "").lower()
        return mapping.get(text, text.replace("_", " ").title() or "—")

    @staticmethod
    def _score(value: Any) -> str:
        if value is None:
            return "—"
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _duration(value: Any) -> str:
        if value is None:
            return "—"
        try:
            milliseconds = max(0, int(value))
        except (TypeError, ValueError):
            return str(value)
        if milliseconds < 1000:
            return f"{milliseconds} ms"
        seconds = milliseconds / 1000.0
        if seconds < 60:
            return f"{seconds:.1f} s"
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {seconds:.0f}s"

    @staticmethod
    def _color_status_item(item: QTableWidgetItem, text: str) -> None:
        value = text.lower()
        if any(token in value for token in ("fail", "error", "critical", "high")):
            item.setForeground(QColor("#B42318"))
        elif any(token in value for token in ("warn", "review", "medium")):
            item.setForeground(QColor("#B54708"))
        elif any(token in value for token in ("pass", "success", "complete", "low")):
            item.setForeground(QColor("#067647"))
