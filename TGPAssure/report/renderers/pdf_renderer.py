from __future__ import annotations

from pathlib import Path
from typing import Any, List
import math
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from report.report_model import ChartSection, HeadingSection, ReportModel, ReportSectionType, TableSection, TextSection


class PdfRenderer:
    def __init__(self, pagesize: str = "a4") -> None:
        base = A4 if pagesize.lower() == "a4" else letter
        self.pagesize = landscape(base)
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(name="ReportTitle", parent=self.styles["Title"], fontSize=22, leading=26, alignment=TA_CENTER, textColor=colors.HexColor("#173A5E"), spaceAfter=18))
        self.styles.add(ParagraphStyle(name="ReportBody", parent=self.styles["BodyText"], fontSize=8.5, leading=11, spaceAfter=5))
        self.styles.add(ParagraphStyle(name="ReportFooter", parent=self.styles["BodyText"], fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#64748B")))

    def render(self, model: ReportModel, output_path: Path) -> Path:
        output_path = Path(output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(output_path),
            pagesize=self.pagesize,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=model.title,
            author="TGPAssure",
        )
        elements: List[Any] = [Paragraph(escape(model.title), self.styles["ReportTitle"])]
        metadata_rows = [[key.replace("_", " ").title(), str(value)] for key, value in model.metadata.items()]
        if metadata_rows:
            elements.append(self._table(["Metadata", "Value"], metadata_rows, [45 * mm, 205 * mm]))
            elements.append(Spacer(1, 6 * mm))
        for section in sorted(model.sections, key=lambda item: item.order):
            self._render_section(section, elements)
        document.build(elements, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        return output_path

    def _page_footer(self, canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(12 * mm, 7 * mm, "TGPAssure QC Report")
        canvas.drawRightString(self.pagesize[0] - 12 * mm, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def _render_section(self, section: Any, elements: List[Any]) -> None:
        if section.section_type == ReportSectionType.HEADING:
            style = self.styles[f"Heading{min(3, max(1, section.level))}"]
            elements.append(Paragraph(escape(section.title), style))
            return
        if section.section_type == ReportSectionType.TEXT:
            style = self.styles["ReportFooter"] if section.style == "footer" else self.styles["ReportBody"]
            elements.append(Paragraph(escape(section.content).replace("\n", "<br/>"), style))
            elements.append(Spacer(1, 2 * mm))
            return
        if section.section_type == ReportSectionType.TABLE:
            if section.headers or section.rows:
                elements.append(self._table(section.headers, section.rows))
                elements.append(Spacer(1, 4 * mm))
            return
        if section.section_type == ReportSectionType.CHART:
            elements.append(self._chart(section))
            elements.append(Spacer(1, 4 * mm))

    def _table(self, headers: List[Any], rows: List[List[Any]], widths: List[float] | None = None) -> Table:
        body_style = self.styles["ReportBody"]
        data: List[List[Any]] = []
        if headers:
            data.append([Paragraph(f"<b>{escape(str(value))}</b>", body_style) for value in headers])
        for row in rows:
            data.append([Paragraph(escape(str(value if value is not None else "")), body_style) for value in row])
        table = Table(data, colWidths=widths, repeatRows=1 if headers else 0, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173A5E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    def _chart(self, section: ChartSection) -> Drawing:
        chart_type = str(section.chart_type or "bar").lower()
        labels = [str(value) for value in section.data.get("labels", [])]
        values = [float(value) for value in section.data.get("values", [])]
        if chart_type in {"pie", "donut"}:
            return self._pie_chart(section, labels, values)
        if chart_type in {"horizontal_bar", "barh", "hbar"} or len(labels) > 8:
            return self._horizontal_bar_chart(section, labels, values)
        return self._vertical_bar_chart(section, labels, values)

    @staticmethod
    def _base_drawing(section: ChartSection, height: float = 74 * mm) -> Drawing:
        width = 245 * mm
        drawing = Drawing(width, height)
        drawing.add(
            String(
                8, height - 12, section.title, fontName="Helvetica-Bold", fontSize=10,
                fillColor=colors.HexColor("#173A5E"),
            )
        )
        return drawing

    def _vertical_bar_chart(self, section: ChartSection, labels: list[str], values: list[float]) -> Drawing:
        drawing = self._base_drawing(section)
        height = drawing.height
        width = drawing.width
        if not values:
            drawing.add(String(8, height / 2, "No chart data available", fontSize=8))
            return drawing
        chart = VerticalBarChart()
        chart.x = 42
        chart.y = 34
        chart.height = height - 65
        chart.width = width - 62
        chart.data = [values]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.angle = 25 if any(len(label) > 10 for label in labels) else 0
        chart.categoryAxis.labels.fontSize = 6
        chart.valueAxis.valueMin = 0
        axis_max, axis_step = self._nice_axis(max(values))
        chart.valueAxis.valueMax = axis_max
        chart.valueAxis.valueStep = axis_step
        chart.valueAxis.labels.fontSize = 6
        chart.bars[0].fillColor = colors.HexColor("#0F6B9A")
        chart.strokeColor = colors.HexColor("#CBD5E1")
        drawing.add(chart)
        if section.y_label:
            drawing.add(String(8, height / 2, section.y_label, fontSize=6, fillColor=colors.HexColor("#475569")))
        if section.x_label:
            drawing.add(String(width / 2 - 20, 5, section.x_label, fontSize=6, fillColor=colors.HexColor("#475569")))
        return drawing

    def _horizontal_bar_chart(self, section: ChartSection, labels: list[str], values: list[float]) -> Drawing:
        height = min(132 * mm, max(74 * mm, (38 + max(1, len(labels)) * 13) * 1.0))
        drawing = self._base_drawing(section, height=height)
        width = drawing.width
        if not values:
            drawing.add(String(8, height / 2, "No chart data available", fontSize=8))
            return drawing
        chart = HorizontalBarChart()
        chart.x = 108
        chart.y = 22
        chart.height = height - 48
        chart.width = width - 132
        chart.data = [values]
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.fontSize = 6
        chart.categoryAxis.labels.dx = -3
        chart.valueAxis.valueMin = 0
        axis_max, axis_step = self._nice_axis(max(values))
        chart.valueAxis.valueMax = axis_max
        chart.valueAxis.valueStep = axis_step
        chart.valueAxis.labels.fontSize = 6
        chart.bars[0].fillColor = colors.HexColor("#0F6B9A")
        chart.strokeColor = colors.HexColor("#CBD5E1")
        drawing.add(chart)
        if section.x_label or section.y_label:
            axis_text = section.x_label or section.y_label
            drawing.add(String(width / 2 - 25, 5, axis_text, fontSize=6, fillColor=colors.HexColor("#475569")))
        return drawing


    @staticmethod
    def _nice_axis(max_value: float, target_steps: int = 5) -> tuple[float, float]:
        """Return human-readable axis bounds (for example 0,20,...,100)."""
        value = max(0.0, float(max_value))
        if value <= 0:
            return 1.0, 1.0
        raw_step = value / max(1, target_steps)
        magnitude = 10 ** math.floor(math.log10(raw_step))
        normalized = raw_step / magnitude
        if normalized <= 1:
            nice = 1
        elif normalized <= 2:
            nice = 2
        elif normalized <= 5:
            nice = 5
        else:
            nice = 10
        step = nice * magnitude
        axis_max = math.ceil(value / step) * step
        return float(axis_max), float(step)

    def _pie_chart(self, section: ChartSection, labels: list[str], values: list[float]) -> Drawing:
        drawing = self._base_drawing(section, height=78 * mm)
        height = drawing.height
        if not values or sum(max(0.0, value) for value in values) <= 0:
            drawing.add(String(8, height / 2, "No chart data available", fontSize=8))
            return drawing
        pie = Pie()
        pie.x = 52
        pie.y = 18
        pie.width = 145
        pie.height = 145
        pie.data = [max(0.0, value) for value in values]
        pie.labels = [f"{label} ({value:g})" for label, value in zip(labels, values)]
        pie.sideLabels = True
        pie.slices.fontSize = 6
        palette = [
            "#0F6B9A", "#2E86AB", "#4FA3C7", "#75B9D4", "#F2A541",
            "#D95D39", "#8F5DA2", "#4F8A5B", "#A7A9AC",
        ]
        for index in range(len(values)):
            pie.slices[index].fillColor = colors.HexColor(palette[index % len(palette)])
            pie.slices[index].strokeColor = colors.white
        drawing.add(pie)
        return drawing
