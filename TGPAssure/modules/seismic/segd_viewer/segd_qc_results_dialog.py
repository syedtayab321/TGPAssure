from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

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
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SegdQcBarChart(QWidget):
    """Compact built-in chart widget for SEG-D QC metrics.

    Matplotlib is deliberately avoided here because this dialog is opened from
    the GUI thread during field review; a lightweight Qt painter keeps the QC
    result dialog responsive inside the packaged EXE.
    """

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._title = title
        self._data: list[tuple[str, float]] = []
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, data: dict[str, Any]) -> None:
        cleaned: list[tuple[str, float]] = []
        for key, value in data.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number < 0:
                continue
            label = str(key).replace("_", " ").title()
            cleaned.append((label, number))
        self._data = cleaned[:10]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        painter.setPen(QColor("#173B53"))
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPointSize(max(9, title_font.pointSize()))
        painter.setFont(title_font)
        painter.drawText(QRectF(10, 6, self.width() - 20, 22), Qt.AlignLeft | Qt.AlignVCenter, self._title)

        if not self._data:
            painter.setPen(QColor("#657B8A"))
            painter.drawText(self.rect().adjusted(10, 32, -10, -10), Qt.AlignCenter, "No numeric QC metrics available")
            painter.end()
            return

        max_value = max(value for _label, value in self._data) or 1.0
        chart = QRectF(10, 36, self.width() - 20, self.height() - 48)
        bar_gap = 5
        bar_height = max(10, int((chart.height() - bar_gap * (len(self._data) - 1)) / len(self._data)))
        label_width = min(138, max(92, int(chart.width() * 0.34)))
        value_width = 64
        bar_left = chart.left() + label_width + 8
        bar_max_width = max(16.0, chart.width() - label_width - value_width - 16)

        body_font = QFont(self.font())
        body_font.setPointSize(max(7, body_font.pointSize() - 1))
        painter.setFont(body_font)
        for index, (label, value) in enumerate(self._data):
            y = chart.top() + index * (bar_height + bar_gap)
            painter.setPen(QColor("#29465A"))
            painter.drawText(QRectF(chart.left(), y, label_width, bar_height), Qt.AlignRight | Qt.AlignVCenter, label)
            width = max(2.0, (value / max_value) * bar_max_width)
            if value == 0:
                fill = QColor("#A9B7C2")
            elif "fail" in label.lower() or "zero" in label.lower() or "resistance" in label.lower() or "leakage" in label.lower():
                fill = QColor("#D97706")
            else:
                fill = QColor("#0A86C7")
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(bar_left, y + 2, width, bar_height - 4), 4, 4)
            painter.setPen(QColor("#102A3D"))
            painter.drawText(QRectF(bar_left + bar_max_width + 8, y, value_width, bar_height), Qt.AlignLeft | Qt.AlignVCenter, f"{value:,.0f}")

        painter.setPen(QPen(QColor("#D4DEE8"), 1))
        painter.drawRect(chart)
        painter.end()


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
        self.setMinimumSize(860, 650)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

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
        root.addWidget(header)

        cards = QGridLayout()
        cards.setHorizontalSpacing(8)
        cards.setVerticalSpacing(8)
        cards.addWidget(self._metric_card("Overall", self.overall_result.upper(), self._result_color(self.overall_result)), 0, 0)
        cards.addWidget(self._metric_card("Score", f"{self.score:.1f}", "#0A86C7"), 0, 1)
        cards.addWidget(self._metric_card("Findings", str(len(self.findings)), "#D97706" if self.findings else "#14804A"), 0, 2)
        cards.addWidget(self._metric_card("Duration", f"{self.duration_ms:,} ms", "#475569"), 0, 3)
        root.addLayout(cards)

        chart_row = QHBoxLayout()
        self.record_chart = SegdQcBarChart("Record / Header Metrics", self)
        self.record_chart.set_data({
            "Physical Traces": self.summary.get("physical_traces", 0),
            "Seismic Traces": self.summary.get("seismic_traces", 0),
            "Auxiliary Traces": self.summary.get("auxiliary_traces", 0),
            "Samples / Trace": self.summary.get("samples_per_trace", 0),
            "Format Code": self.summary.get("format_code", 0),
        })
        self.trace_chart = SegdQcBarChart("Trace QC Flags", self)
        flagged = dict(self.summary.get("flagged_trace_statuses") or {})
        flagged["Zero Trace Count"] = self._metric_from_stages("zero_trace_count")
        self.trace_chart.set_data(flagged)
        chart_row.addWidget(self.record_chart, 1)
        chart_row.addWidget(self.trace_chart, 1)
        root.addLayout(chart_row)

        table_row = QHBoxLayout()
        self.stage_table = QTableWidget(self)
        self.stage_table.setColumnCount(5)
        self.stage_table.setHorizontalHeaderLabels(["Stage", "Result", "Score", "Metrics", "Message"])
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.stage_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.stage_table.setAlternatingRowColors(True)
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
        self._populate_finding_table()

        left_panel = self._panel("QC Stages", self.stage_table)
        right_panel = self._panel("Findings / Review Actions", self.finding_table)
        table_row.addWidget(left_panel, 1)
        table_row.addWidget(right_panel, 1)
        root.addLayout(table_row, 1)

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
        root.addLayout(footer)

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
        )

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
                stage.get("stage_name") or stage.get("stage_key") or "—",
                str(stage.get("result") or "—").upper(),
                f"{float(stage.get('score') or 0):.1f}",
                json.dumps(stage.get("metrics") or {}, ensure_ascii=False, default=str),
                stage.get("message") or "—",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    item.setForeground(QColor(self._result_color(str(stage.get("result") or ""))))
                    font = item.font(); font.setBold(True); item.setFont(font)
                self.stage_table.setItem(row, col, item)

    def _populate_finding_table(self) -> None:
        self.finding_table.setRowCount(max(1, len(self.findings)))
        if not self.findings:
            self.finding_table.setItem(0, 0, QTableWidgetItem("PASS"))
            self.finding_table.setItem(0, 1, QTableWidgetItem("—"))
            self.finding_table.setItem(0, 2, QTableWidgetItem("—"))
            self.finding_table.setItem(0, 3, QTableWidgetItem("No review finding detected."))
            self.finding_table.setItem(0, 4, QTableWidgetItem("No corrective action required."))
            return
        for row, finding in enumerate(self.findings):
            values = [
                str(finding.get("severity") or "warning").upper(),
                finding.get("category") or "—",
                finding.get("code") or "—",
                finding.get("title") or finding.get("description") or "Review required",
                finding.get("suggested_action") or "Review source data and acquisition notes.",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    severity = str(finding.get("severity") or "warning").lower()
                    item.setForeground(QColor("#B42318" if severity == "error" else "#B54708"))
                    font = item.font(); font.setBold(True); item.setFont(font)
                self.finding_table.setItem(row, col, item)

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
