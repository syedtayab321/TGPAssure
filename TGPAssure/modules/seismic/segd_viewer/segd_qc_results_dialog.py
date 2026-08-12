from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Chart / indicator widgets
# ---------------------------------------------------------------------------


class DynamicBarChart(pg.PlotWidget):
    """Auto-scaling bar chart that plots every numeric value it is given.

    No cap on the number of bars: the chart widens as data grows and is
    meant to be placed inside a horizontally-scrolling QScrollArea (see
    SegdQcResultsDialog._wrap_scrollable). Colors follow the same
    fail/zero/leakage-highlighting convention as before.
    """

    BAR_WIDTH = 0.6
    PIXELS_PER_BAR = 58
    MIN_WIDTH = 380
    WARN_TERMS = ("fail", "zero", "resistance", "leakage", "error", "bad")

    def __init__(self, title: str, parent: Optional[QWidget] = None, height: int = 230) -> None:
        super().__init__(parent)
        self._title = title
        self._chart_height = height
        self.setBackground("#FFFFFF")
        self.showGrid(x=False, y=True, alpha=0.15)
        plot_item = self.getPlotItem()
        plot_item.setTitle(title, color="#173B53", size="10pt")
        plot_item.getAxis("left").setTextPen("#29465A")
        plot_item.getAxis("bottom").setTextPen("#29465A")
        plot_item.getAxis("left").setPen("#D4DEE8")
        plot_item.getAxis("bottom").setPen("#D4DEE8")
        self.setMouseEnabled(x=False, y=False)
        plot_item.hideButtons()
        plot_item.setMenuEnabled(False)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setMinimumWidth(self.MIN_WIDTH)

    def set_data(self, data: dict[str, Any]) -> None:
        plot_item = self.getPlotItem()
        plot_item.clear()
        plot_item.showAxis("bottom")
        plot_item.showAxis("left")

        cleaned: list[tuple[str, float]] = []
        for key, value in data.items():
            if isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number < 0:
                continue
            label = str(key).replace("_", " ").title()
            cleaned.append((label, number))

        if not cleaned:
            plot_item.hideAxis("bottom")
            plot_item.hideAxis("left")
            empty_text = pg.TextItem("No numeric QC metrics available", color="#657B8A", anchor=(0.5, 0.5))
            plot_item.addItem(empty_text)
            empty_text.setPos(0, 0)
            self.setXRange(-1, 1)
            self.setYRange(-1, 1)
            self.setMinimumWidth(self.MIN_WIDTH)
            return

        xs = list(range(len(cleaned)))
        heights = [value for _label, value in cleaned]
        colors: list[str] = []
        for label, value in cleaned:
            lower = label.lower()
            if value == 0:
                colors.append("#A9B7C2")
            elif any(term in lower for term in self.WARN_TERMS):
                colors.append("#D97706")
            else:
                colors.append("#0A86C7")

        bar_item = pg.BarGraphItem(x=xs, height=heights, width=self.BAR_WIDTH, brushes=colors, pen=pg.mkPen(None))
        plot_item.addItem(bar_item)

        max_height = max(heights) if heights else 1.0
        for x, (_label, value) in zip(xs, cleaned):
            value_text = pg.TextItem(f"{value:,.0f}", color="#102A3D", anchor=(0.5, 1.0))
            value_text.setPos(x, value + max_height * 0.02)
            plot_item.addItem(value_text)

        # pyqtgraph's AxisItem has no built-in rotated-label support (no
        # "tickTextAngle" style key), so the default tick text is suppressed
        # and rotated labels are drawn manually with pg.TextItem instead,
        # which does support rotation via its angle argument.
        axis = plot_item.getAxis("bottom")
        axis.setTicks([[(x, "") for x in xs]])

        label_font = QFont(self.font())
        label_font.setPointSize(7)
        bottom_pad = -(max_height * 0.42) if max_height else -0.5
        label_y = bottom_pad * 0.15
        for x, (label, _value) in zip(xs, cleaned):
            label_text = pg.TextItem(label, color="#29465A", anchor=(1, 1), angle=40)
            label_text.setFont(label_font)
            label_text.setPos(x + 0.05, label_y)
            plot_item.addItem(label_text)

        self.setYRange(bottom_pad, max_height * 1.2 if max_height else 1, padding=0)
        self.setXRange(-0.6, len(cleaned) - 0.4, padding=0)
        self.setMinimumWidth(max(self.MIN_WIDTH, len(cleaned) * self.PIXELS_PER_BAR))


class ScoreGaugeWidget(QWidget):
    """Semicircular 0-100 QC score gauge (red / amber / green banded)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._score = 0.0
        self.setMinimumSize(190, 150)

    def set_score(self, score: float) -> None:
        self._score = max(0.0, min(100.0, float(score)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        diameter = min(self.width() - 28, (self.height() - 52) * 2)
        diameter = max(60, diameter)
        gauge_rect = QRectF((self.width() - diameter) / 2, 12, diameter, diameter)

        pen_bg = QPen(QColor("#E3EAF0"), 14, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(gauge_rect, 0 * 16, 180 * 16)

        if self._score >= 80:
            color = QColor("#14804A")
        elif self._score >= 50:
            color = QColor("#D97706")
        else:
            color = QColor("#B42318")
        span_angle = int(180 * (self._score / 100.0))
        if span_angle > 0:
            pen_fg = QPen(color, 14, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen_fg)
            painter.drawArc(gauge_rect, 180 * 16, -span_angle * 16)

        value_rect = QRectF(gauge_rect.left(), gauge_rect.center().y() - 14, gauge_rect.width(), 28)
        painter.setPen(QColor("#102A3D"))
        value_font = QFont(self.font())
        value_font.setBold(True)
        value_font.setPointSize(17)
        painter.setFont(value_font)
        painter.drawText(value_rect, Qt.AlignCenter, f"{self._score:.0f}")

        caption_font = QFont(self.font())
        caption_font.setPointSize(8)
        caption_font.setBold(True)
        painter.setFont(caption_font)
        painter.setPen(QColor("#657B8A"))
        painter.drawText(QRectF(0, gauge_rect.center().y() + 18, self.width(), 16), Qt.AlignHCenter, "QC SCORE")
        painter.end()


class ResultDonutWidget(QWidget):
    """Donut chart of stage results: Pass / Warn / Fail counts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._counts: dict[str, int] = {"PASS": 0, "WARN": 0, "FAIL": 0}
        self.setMinimumSize(190, 150)

    def set_counts(self, pass_count: int, warn_count: int, fail_count: int) -> None:
        self._counts = {"PASS": pass_count, "WARN": warn_count, "FAIL": fail_count}
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        total = sum(self._counts.values())
        diameter = min(self.width() - 20, self.height() - 46)
        diameter = max(60, diameter)
        rect = QRectF((self.width() - diameter) / 2, 8, diameter, diameter).adjusted(8, 8, -8, -8)

        colors = {"PASS": QColor("#14804A"), "WARN": QColor("#D97706"), "FAIL": QColor("#B42318")}
        if total == 0:
            painter.setPen(QPen(QColor("#E3EAF0"), 16))
            painter.drawEllipse(rect)
        else:
            start = 90 * 16
            for key in ("PASS", "WARN", "FAIL"):
                count = self._counts.get(key, 0)
                if not count:
                    continue
                span = int(360 * 16 * (count / total))
                painter.setPen(QPen(colors[key], 16, Qt.SolidLine, Qt.FlatCap))
                painter.drawArc(rect, start, -span)
                start -= span

        pass_pct = f"{(self._counts.get('PASS', 0) / total * 100):.0f}%" if total else "\u2014"
        value_font = QFont(self.font())
        value_font.setBold(True)
        value_font.setPointSize(14)
        painter.setFont(value_font)
        painter.setPen(QColor("#102A3D"))
        painter.drawText(rect, Qt.AlignCenter, pass_pct)

        legend_font = QFont(self.font())
        legend_font.setPointSize(7)
        painter.setFont(legend_font)
        legend_y = rect.bottom() + 6
        x = (self.width() - 165) / 2
        for label, color in (("PASS", colors["PASS"]), ("WARN", colors["WARN"]), ("FAIL", colors["FAIL"])):
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRect(QRectF(x, legend_y, 8, 8))
            painter.setPen(QColor("#29465A"))
            painter.drawText(QRectF(x + 11, legend_y - 3, 45, 14), Qt.AlignLeft | Qt.AlignVCenter, label)
            x += 55
        painter.end()


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------


class SegdQcResultsDialog(QDialog):
    def __init__(
        self,
        *,
        file_path: Path,
        qc_type: str,
        summary: dict[str, Any],
        stages: list[dict[str, Any]],
        findings: list[dict[str, Any]],
        overall_result: str,
        score: float,
        run_uuid: str = "",
        duration_ms: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.qc_type = qc_type
        self.summary = summary
        self.stages = stages
        self.findings = findings
        self.overall_result = overall_result
        self.score = score
        self.run_uuid = run_uuid
        self.duration_ms = duration_ms
        self.setWindowTitle(f"SEG-D {qc_type.title()} QC Results")
        self.setMinimumSize(1040, 800)
        self.resize(1100, 840)
        self._setup_ui()

    # -- layout -------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        body = QVBoxLayout(scroll_content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        body.addLayout(self._build_metric_cards())
        body.addWidget(self._build_overview_row())
        body.addLayout(self._build_main_charts())

        stage_charts_row = self._build_stage_charts()
        if stage_charts_row is not None:
            body.addWidget(self._panel("Per-Stage Metrics", stage_charts_row))

        body.addLayout(self._build_tables())
        body.addWidget(self._build_all_metrics_panel())

        scroll_area.setWidget(scroll_content)
        root.addWidget(scroll_area, 1)

        root.addLayout(self._build_footer())

        self.setStyleSheet(
            "QDialog{background:#F3F7FA;color:#102A3D;}"
            "QFrame#qcHeader{background:#102A3D;border:1px solid #284B63;border-radius:10px;}"
            "QLabel#qcTitle{color:white;font-size:16pt;font-weight:900;background:transparent;}"
            "QLabel#qcSubtitle{color:#CFE7F5;font-size:9pt;background:transparent;}"
            "QFrame#metricCard{background:white;border:1px solid #D4DEE8;border-radius:8px;}"
            "QLabel#metricCaption{color:#607080;font-size:8pt;font-weight:800;background:transparent;}"
            "QLabel#metricValue{font-size:15pt;font-weight:900;background:transparent;}"
            "QFrame#panel{background:white;border:1px solid #D4DEE8;border-radius:8px;}"
            "QLabel#panelTitle{color:#173B53;font-weight:900;background:transparent;}"
            "QTableWidget{background:white;alternate-background-color:#F5F8FA;gridline-color:#DDE6EE;font-size:8pt;}"
            "QHeaderView::section{background:#173B53;color:white;padding:5px;border:0;font-weight:800;}"
            "QPushButton{background:#FFFFFF;border:1px solid #BFD0DC;border-radius:5px;padding:6px 11px;font-weight:800;}"
            "QPushButton:hover{background:#EFF8FC;border-color:#0A86C7;}"
            "QScrollArea{background:transparent;border:0;}"
        )

    def _build_header(self) -> QFrame:
        header = QFrame(self)
        header.setObjectName("qcHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        title = QLabel(f"SEG-D {self.qc_type.title()} QC Results")
        title.setObjectName("qcTitle")
        subtitle = QLabel(str(self.file_path))
        subtitle.setObjectName("qcSubtitle")
        subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        return header

    def _build_metric_cards(self) -> QGridLayout:
        stage_results = [str(stage.get("result") or "").lower() for stage in self.stages]
        pass_count = sum(1 for r in stage_results if r == "pass")
        fail_count = sum(1 for r in stage_results if r == "fail")

        cards = QGridLayout()
        cards.setHorizontalSpacing(8)
        cards.setVerticalSpacing(8)
        cards.addWidget(self._metric_card("Overall", self.overall_result.upper(), self._result_color(self.overall_result)), 0, 0)
        cards.addWidget(self._metric_card("Score", f"{self.score:.1f}", "#0A86C7"), 0, 1)
        cards.addWidget(self._metric_card("Findings", str(len(self.findings)), "#D97706" if self.findings else "#14804A"), 0, 2)
        cards.addWidget(self._metric_card("Duration", f"{self.duration_ms:,} ms", "#475569"), 0, 3)
        cards.addWidget(
            self._metric_card("Stages Passed", f"{pass_count}/{len(self.stages)}", "#B42318" if fail_count else "#14804A"),
            0,
            4,
        )
        return cards

    def _build_overview_row(self) -> QFrame:
        stage_results = [str(stage.get("result") or "").lower() for stage in self.stages]
        pass_count = sum(1 for r in stage_results if r == "pass")
        fail_count = sum(1 for r in stage_results if r == "fail")
        warn_count = len(stage_results) - pass_count - fail_count

        self.gauge = ScoreGaugeWidget(self)
        self.gauge.set_score(self.score)
        self.donut = ResultDonutWidget(self)
        self.donut.set_counts(pass_count, warn_count, fail_count)

        row = QHBoxLayout()
        row.addWidget(self._panel("QC Score", self.gauge))
        row.addWidget(self._panel("Stage Result Breakdown", self.donut))
        row.addStretch(1)

        wrapper = QFrame(self)
        wrapper.setObjectName("panel")
        wrapper.setStyleSheet("QFrame#panel{border:0;background:transparent;}")
        wrapper.setLayout(row)
        return wrapper

    def _build_main_charts(self) -> QHBoxLayout:
        self.summary_chart = DynamicBarChart("Summary Metrics (all numeric values)", self, height=240)
        self.summary_chart.set_data(dict(self.summary))

        flagged = dict(self.summary.get("flagged_trace_statuses") or {})
        flagged["Zero Trace Count"] = self._metric_from_stages("zero_trace_count")
        self.trace_chart = DynamicBarChart("Trace QC Flags", self, height=240)
        self.trace_chart.set_data(flagged)

        row = QHBoxLayout()
        row.addWidget(self._wrap_scrollable(self.summary_chart, 240), 1)
        row.addWidget(self._wrap_scrollable(self.trace_chart, 240), 1)
        return row

    def _build_stage_charts(self) -> Optional[QScrollArea]:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        has_any = False
        for stage in self.stages:
            metrics = stage.get("metrics") or {}
            numeric_metrics = {
                key: value for key, value in metrics.items() if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            if not numeric_metrics:
                continue
            has_any = True
            stage_name = str(stage.get("stage_name") or stage.get("stage_key") or "Stage")
            chart = DynamicBarChart(stage_name, self, height=190)
            chart.set_data(numeric_metrics)
            layout.addWidget(chart)
        layout.addStretch(1)

        if not has_any:
            return None

        scroll = QScrollArea(self)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(212)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _build_tables(self) -> QHBoxLayout:
        self.stage_table = QTableWidget(self)
        self.stage_table.setColumnCount(5)
        self.stage_table.setHorizontalHeaderLabels(["Stage", "Result", "Score", "Metrics", "Message"])
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.stage_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.stage_table.setAlternatingRowColors(True)
        self.stage_table.setMinimumHeight(260)
        self._populate_stage_table()

        self.finding_table = QTableWidget(self)
        self.finding_table.setColumnCount(5)
        self.finding_table.setHorizontalHeaderLabels(["Severity", "Category", "Code", "Finding", "Action"])
        self.finding_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.finding_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.finding_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.finding_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.finding_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.finding_table.setAlternatingRowColors(True)
        self.finding_table.setMinimumHeight(260)
        self._populate_finding_table()

        row = QHBoxLayout()
        row.addWidget(self._panel("QC Stages", self.stage_table), 1)
        row.addWidget(self._panel("Findings / Review Actions", self.finding_table), 1)
        return row

    def _build_all_metrics_panel(self) -> QFrame:
        self.all_metrics_table = QTableWidget(self)
        self.all_metrics_table.setColumnCount(3)
        self.all_metrics_table.setHorizontalHeaderLabels(["Source", "Metric", "Value"])
        self.all_metrics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.all_metrics_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.all_metrics_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.all_metrics_table.setAlternatingRowColors(True)
        self.all_metrics_table.setSortingEnabled(True)
        self.all_metrics_table.setMinimumHeight(260)
        self._populate_all_metrics_table()
        return self._panel("All Metrics (complete, unfiltered)", self.all_metrics_table)

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Export saves the same results shown here for client/reviewer documentation."))
        footer.addStretch(1)
        export_csv = QPushButton("Export CSV")
        export_json = QPushButton("Export JSON")
        copy_summary = QPushButton("Copy Summary")
        close = QPushButton("Close")
        export_csv.clicked.connect(self.export_csv)
        export_json.clicked.connect(self.export_json)
        copy_summary.clicked.connect(self.copy_summary)
        close.clicked.connect(self.accept)
        footer.addWidget(export_csv)
        footer.addWidget(export_json)
        footer.addWidget(copy_summary)
        footer.addWidget(close)
        return footer

    # -- small helpers --------------------------------------------------

    def _wrap_scrollable(self, widget: QWidget, height: int) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(height + 18)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _panel(self, title: str, child: QWidget) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        label = QLabel(title)
        label.setObjectName("panelTitle")
        layout.addWidget(label)
        layout.addWidget(child, 1)
        return panel

    def _metric_card(self, caption: str, value: str, color: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        cap = QLabel(caption)
        cap.setObjectName("metricCaption")
        val = QLabel(value)
        val.setObjectName("metricValue")
        val.setStyleSheet(f"color:{color};")
        layout.addWidget(cap)
        layout.addWidget(val)
        return card

    def _populate_stage_table(self) -> None:
        self.stage_table.setRowCount(len(self.stages))
        for row, stage in enumerate(self.stages):
            values = [
                stage.get("stage_name") or stage.get("stage_key") or "\u2014",
                str(stage.get("result") or "\u2014").upper(),
                f"{float(stage.get('score') or 0):.1f}",
                json.dumps(stage.get("metrics") or {}, ensure_ascii=False, default=str),
                stage.get("message") or "\u2014",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    item.setForeground(QColor(self._result_color(str(stage.get("result") or ""))))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.stage_table.setItem(row, col, item)

    def _populate_finding_table(self) -> None:
        self.finding_table.setRowCount(max(1, len(self.findings)))
        if not self.findings:
            self.finding_table.setItem(0, 0, QTableWidgetItem("PASS"))
            self.finding_table.setItem(0, 1, QTableWidgetItem("\u2014"))
            self.finding_table.setItem(0, 2, QTableWidgetItem("\u2014"))
            self.finding_table.setItem(0, 3, QTableWidgetItem("No review finding detected."))
            self.finding_table.setItem(0, 4, QTableWidgetItem("No corrective action required."))
            return
        for row, finding in enumerate(self.findings):
            values = [
                str(finding.get("severity") or "warning").upper(),
                finding.get("category") or "\u2014",
                finding.get("code") or "\u2014",
                finding.get("title") or finding.get("description") or "Review required",
                finding.get("suggested_action") or "Review source data and acquisition notes.",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    severity = str(finding.get("severity") or "warning").lower()
                    item.setForeground(QColor("#B42318" if severity == "error" else "#B54708"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.finding_table.setItem(row, col, item)

    def _flatten_metrics(self) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for key, value in self.summary.items():
            rows.append(("Summary", str(key).replace("_", " ").title(), self._format_value(value)))
        for stage in self.stages:
            stage_name = str(stage.get("stage_name") or stage.get("stage_key") or "Stage")
            metrics = stage.get("metrics") or {}
            for key, value in metrics.items():
                rows.append((stage_name, str(key).replace("_", " ").title(), self._format_value(value)))
        return rows

    def _populate_all_metrics_table(self) -> None:
        rows = self._flatten_metrics()
        self.all_metrics_table.setSortingEnabled(False)
        self.all_metrics_table.setRowCount(len(rows))
        for row, (source, key, value) in enumerate(rows):
            self.all_metrics_table.setItem(row, 0, QTableWidgetItem(source))
            self.all_metrics_table.setItem(row, 1, QTableWidgetItem(key))
            self.all_metrics_table.setItem(row, 2, QTableWidgetItem(value))
        self.all_metrics_table.setSortingEnabled(True)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, float):
            text = f"{value:,.3f}".rstrip("0").rstrip(".")
            return text if text else "0"
        return str(value)

    def _metric_from_stages(self, key: str) -> Any:
        for stage in self.stages:
            metrics = stage.get("metrics") or {}
            if key in metrics:
                return metrics[key]
        return 0

    @staticmethod
    def _result_color(result: str) -> str:
        clean = result.lower()
        if clean == "pass":
            return "#14804A"
        if clean == "fail":
            return "#B42318"
        return "#D97706"

    # -- export -----------------------------------------------------

    def _export_payload(self) -> dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "qc_type": self.qc_type,
            "overall_result": self.overall_result,
            "score": self.score,
            "duration_ms": self.duration_ms,
            "run_uuid": self.run_uuid,
            "summary": self.summary,
            "stages": self.stages,
            "findings": self.findings,
        }

    def export_json(self) -> None:
        default = self.file_path.with_name(f"{self.file_path.stem}_{self.qc_type}_qc_results.json")
        path, _ = QFileDialog.getSaveFileName(self, "Export SEG-D QC JSON", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self._export_payload(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception as error:
            QMessageBox.critical(self, "Export SEG-D QC", str(error))

    def export_csv(self) -> None:
        default = self.file_path.with_name(f"{self.file_path.stem}_{self.qc_type}_qc_results.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export SEG-D QC CSV", str(default), "CSV (*.csv)")
        if not path:
            return
        try:
            with Path(path).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["section", "key", "value"])
                writer.writerow(["summary", "file_path", str(self.file_path)])
                writer.writerow(["summary", "qc_type", self.qc_type])
                writer.writerow(["summary", "overall_result", self.overall_result])
                writer.writerow(["summary", "score", self.score])
                writer.writerow(["summary", "duration_ms", self.duration_ms])
                for key, value in self.summary.items():
                    writer.writerow(["summary", key, json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else value])
                writer.writerow([])
                writer.writerow(["stage", "result", "score", "metrics", "message"])
                for stage in self.stages:
                    writer.writerow([
                        stage.get("stage_name") or stage.get("stage_key"),
                        stage.get("result"),
                        stage.get("score"),
                        json.dumps(stage.get("metrics") or {}, ensure_ascii=False, default=str),
                        stage.get("message"),
                    ])
                writer.writerow([])
                writer.writerow(["severity", "category", "code", "title", "description", "suggested_action"])
                for finding in self.findings:
                    writer.writerow([
                        finding.get("severity"), finding.get("category"), finding.get("code"),
                        finding.get("title"), finding.get("description"), finding.get("suggested_action"),
                    ])
        except Exception as error:
            QMessageBox.critical(self, "Export SEG-D QC", str(error))

    def copy_summary(self) -> None:
        lines = [
            f"SEG-D {self.qc_type.title()} QC Results",
            f"File: {self.file_path}",
            f"Overall: {self.overall_result.upper()}",
            f"Score: {self.score:.1f}",
            f"Findings: {len(self.findings)}",
        ]
        for key, value in self.summary.items():
            lines.append(f"{key}: {value}")
        QApplication.clipboard().setText("\n".join(lines))