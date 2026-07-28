from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from modules.electrical.models import ElectricalQcResult
from report.report_model import ChartSection, HeadingSection, ReportModel, TableSection, TextSection
from report.renderers.pdf_renderer import PdfRenderer
from report.renderers.xlsx_renderer import XlsxRenderer


class ElectricalReportBuilder:
    def build_model(self, result: ElectricalQcResult) -> ReportModel:
        summary = result.summary()
        model = ReportModel(f"TGPAssure Electrical QC Report — {result.dataset.method_label}")
        model.metadata = {
            "source_file": result.dataset.source_path.name,
            "method": result.dataset.method_label,
            "records": result.dataset.record_count,
            "overall_status": result.status.upper(),
            "qc_score": f"{result.score:.1f}/100",
            "profile": result.profile_name,
            "duration_ms": result.duration_ms,
        }
        model.add_section(HeadingSection("Executive QC Assessment", 1))
        model.add_section(TextSection(
            "Assessment",
            f"Automated electrical QC completed with status {result.status.upper()} and score {result.score:.1f}/100. "
            "The checks cover file/schema integrity, electrode geometry, signal/contact/stacking diagnostics, apparent resistivity, "
            "reciprocity/repeatability and method-specific controls. Automated screening does not by itself validate an inversion or geological interpretation.",
        ))
        model.add_section(TableSection(
            "Dataset Overview",
            ["Item", "Value"],
            [["Source", str(result.dataset.source_path)], ["Method", result.dataset.method_label],
             ["Records", result.dataset.record_count], ["Fields", ", ".join(sorted(result.dataset.columns))]],
        ))

        status_counts = summary.get("stage_status_counts", {})
        model.add_section(ChartSection(
            "QC Stage Status Distribution", "pie",
            {"labels": [str(k).title() for k in status_counts], "values": [status_counts[k] for k in status_counts]},
        ))
        model.add_section(ChartSection(
            "QC Stage Scores", "horizontal_bar",
            {"labels": [stage.stage_name for stage in result.stages], "values": [round(stage.score, 2) for stage in result.stages]},
            x_label="Score", y_label="QC stage",
        ))
        model.add_section(ChartSection(
            "QC Stage Duration", "horizontal_bar",
            {"labels": [stage.stage_name for stage in result.stages], "values": [stage.duration_ms for stage in result.stages]},
            x_label="Milliseconds", y_label="QC stage",
        ))

        severity_counts = summary.get("severity_counts", {})
        if severity_counts:
            model.add_section(ChartSection(
                "QC Finding Severity Distribution", "pie",
                {"labels": [str(key).title() for key in severity_counts], "values": [severity_counts[key] for key in severity_counts]},
            ))

        array_counts = result.dataset.metadata.get("array_type_counts", {})
        if isinstance(array_counts, dict) and array_counts:
            model.add_section(ChartSection(
                "Electrode Array Distribution", "horizontal_bar",
                {"labels": [str(key) for key in array_counts], "values": [float(array_counts[key]) for key in array_counts]},
                x_label="Measurement count", y_label="Array",
            ))

        reciprocal_chart = _reciprocal_chart(result)
        if reciprocal_chart is not None:
            model.add_section(reciprocal_chart)

        method_chart = _method_qc_chart(result)
        if method_chart is not None:
            model.add_section(method_chart)

        statistics_rows = _measurement_statistics(result)
        if statistics_rows:
            model.add_section(TableSection(
                "Electrical Measurement Statistics", ["Measurement", "Valid", "P05", "Median", "P95"], statistics_rows
            ))

        model.add_section(HeadingSection("QC Stage Results", 1))
        stage_rows: list[list[Any]] = []
        for index, stage in enumerate(result.stages, start=1):
            stage_rows.append([index, stage.stage_name, stage.status.upper(), f"{stage.score:.1f}", len(stage.findings), stage.message])
        model.add_section(TableSection("Stages", ["#", "Stage", "Status", "Score", "Findings", "Summary"], stage_rows))

        model.add_section(HeadingSection("QC Findings and Corrective Actions", 1))
        finding_rows: list[list[Any]] = []
        for finding in result.findings:
            finding_rows.append([
                finding.severity.upper(), finding.stage_key, finding.code, finding.title,
                finding.message, finding.suggested_action,
            ])
        if not finding_rows:
            finding_rows = [["INFO", "summary", "—", "No automated findings", "No QC issues were generated.", "Continue competent review/inversion diagnostics."]]
        model.add_section(TableSection(
            "Findings", ["Severity", "Stage", "Code", "Title", "Finding", "Recommended action"], finding_rows,
        ))

        model.add_section(HeadingSection("Detailed Metrics", 1))
        metric_rows: list[list[Any]] = []
        for stage in result.stages:
            for key, value in stage.metrics.items():
                metric_rows.append([stage.stage_name, key.replace("_", " ").title(), _format(value)])
        model.add_section(TableSection("Metrics", ["Stage", "Metric", "Value"], metric_rows))

        model.add_section(HeadingSection("QC Profile Thresholds", 1))
        model.add_section(TableSection(
            "Configured Thresholds", ["Parameter", "Value"],
            [[key.replace("_", " ").title(), value] for key, value in sorted(result.thresholds.items())],
        ))
        model.add_section(TextSection(
            "Interpretation Note",
            "Electrical apparent-resistivity/IP/SP/MALM anomalies are non-unique. Final acceptance requires review of acquisition notes, "
            "array sensitivity, topography, reciprocal/repeat errors, inversion misfit/sensitivity and geological context. "
            "Pseudosections are visualization aids and are not inverted subsurface models.",
            style="footer",
        ))
        return model

    def render(self, result: ElectricalQcResult, output_path: str | Path, fmt: str) -> Path:
        output = Path(output_path).expanduser().resolve()
        model = self.build_model(result)
        if fmt.lower() == "pdf":
            return PdfRenderer().render(model, output)
        if fmt.lower() in {"xlsx", "excel"}:
            return XlsxRenderer().render(model, output)
        raise ValueError(f"Unsupported electrical report format: {fmt}")


def _format(value: Any) -> str:
    if isinstance(value, float):
        if value != value:
            return "N/A"
        return f"{value:.5g}"
    return str(value)


def _reciprocal_chart(result: ElectricalQcResult) -> ChartSection | None:
    if not result.dataset.has("reciprocal_error_pct"):
        return None
    values = result.dataset.numeric("reciprocal_error_pct")
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    warn = float(result.thresholds.get("reciprocal_warn_pct", 5.0))
    fail = float(result.thresholds.get("reciprocal_fail_pct", 10.0))
    counts = [
        int(np.count_nonzero(values <= warn)),
        int(np.count_nonzero((values > warn) & (values <= fail))),
        int(np.count_nonzero(values > fail)),
    ]
    return ChartSection(
        "Reciprocal Error Screening", "bar",
        {"labels": [f"≤ {warn:g}%", f"{warn:g}–{fail:g}%", f"> {fail:g}%"], "values": counts},
        x_label="Configured screening band", y_label="Readings",
    )


def _method_qc_chart(result: ElectricalQcResult) -> ChartSection | None:
    dataset = result.dataset
    if dataset.method.value in {"fdip", "sip"} and dataset.has("frequency_hz"):
        frequency = dataset.numeric("frequency_hz")
        frequency = frequency[np.isfinite(frequency) & (frequency > 0)]
        if frequency.size:
            unique, counts = np.unique(frequency, return_counts=True)
            if unique.size > 20:
                order = np.argsort(counts)[-20:]
                unique, counts = unique[order], counts[order]
            return ChartSection(
                "Frequency Coverage", "bar",
                {"labels": [f"{value:g}" for value in unique], "values": [int(value) for value in counts]},
                x_label="Frequency (Hz)", y_label="Measurement count",
            )
    if dataset.method.value == "tdip":
        windows = sorted(name for name in dataset.columns if name.startswith("window_") or name.startswith("decay_"))
        medians: list[float] = []
        labels: list[str] = []
        for name in windows[:20]:
            values = np.abs(dataset.numeric(name))
            values = values[np.isfinite(values)]
            if values.size:
                labels.append(name.replace("_", " ").title())
                medians.append(float(np.median(values)))
        if medians:
            return ChartSection(
                "TDIP Decay Window Median Magnitudes", "bar",
                {"labels": labels, "values": medians},
                x_label="Decay window", y_label="Median absolute response",
            )
    return None


def _measurement_statistics(result: ElectricalQcResult) -> list[list[Any]]:
    dataset = result.dataset
    candidates = (
        "apparent_resistivity_ohm_m", "chargeability_mv_v", "sp_mv", "sp_corrected_mv",
        "phase_mrad", "frequency_hz", "current_ma", "voltage_mv", "contact_resistance_ohm",
        "stack_std_pct", "electric_field_mv_km", "electric_field_x_mv_km", "electric_field_y_mv_km",
    )
    rows: list[list[Any]] = []
    for name in candidates:
        if not dataset.has(name):
            continue
        values = dataset.numeric(name)
        values = values[np.isfinite(values)]
        if values.size == 0:
            continue
        p05, median, p95 = np.percentile(values, [5, 50, 95])
        rows.append([name.replace("_", " ").title(), int(values.size), _format(float(p05)), _format(float(median)), _format(float(p95))])
    return rows
