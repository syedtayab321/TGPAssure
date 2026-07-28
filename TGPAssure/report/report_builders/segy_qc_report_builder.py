from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from report.report_model import ChartSection, HeadingSection, ReportModel, TableSection, TextSection


class SegyQcReportBuilder:
    """Build an in-depth SEG-Y QC report model.

    The builder keeps the existing public API but expands the report into an
    executive assessment, data inventory, QC overview charts, processing-stage
    summaries, findings/corrective actions, detailed stage metrics, thresholds
    and final acceptance recommendations.
    """

    STATUS_ORDER = ("pass", "warn", "fail", "skipped", "error", "pending")
    SEVERITY_ORDER = ("critical", "error", "warning", "warn", "info")

    STAGE_GROUPS = (
        (
            "File, Header and Structural Integrity",
            ("file_integrity", "textual", "binary", "trace_header", "header", "integrity"),
        ),
        (
            "Geometry, Coordinates and Navigation",
            ("geometry", "coordinate", "navigation", "spatial"),
        ),
        (
            "Trace, Amplitude and Noise",
            ("trace", "dead", "zero", "noise", "clipping", "spike", "dc_bias", "amplitude", "rms", "energy"),
        ),
        (
            "Frequency, Timing and Statics",
            ("frequency", "bandwidth", "timing", "statics", "residual_static"),
        ),
        (
            "Velocity, NMO, Stack and Migration",
            ("velocity", "nmo", "stack", "migration"),
        ),
        (
            "Post-Stack Attributes and 4D Repeatability",
            ("attribute", "coherence", "semblance", "repeatability", "4d", "time_lapse", "time-lapse"),
        ),
    )

    def build(
        self,
        payload_or_summary: Dict[str, Any],
        stage_results: Optional[List[Dict[str, Any]]] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> ReportModel:
        run, stages, finding_rows = self._normalize_payload(payload_or_summary, stage_results, findings)

        summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
        parameters = run.get("parameters") if isinstance(run.get("parameters"), dict) else {}
        source_path = run.get("source_file_path") or run.get("file_path") or summary.get("file_path") or "Unknown"
        overall_result = run.get("overall_result") or summary.get("overall_result") or run.get("overall_status") or run.get("status") or "unknown"
        score = run.get("score") if run.get("score") is not None else summary.get("score")
        run_uuid = run.get("run_uuid") or summary.get("run_uuid") or ""
        profile = run.get("qc_profile") or summary.get("profile_name") or "Unknown"

        model = ReportModel("TGPAssure SEG-Y Quality Control Report")
        model.metadata = {
            "run_uuid": run_uuid,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(source_path),
            "profile": profile,
            "overall_result": str(overall_result).upper(),
            "score": score if score is not None else "N/A",
        }

        # --------------------------------------------------------------
        # Cover / purpose / executive assessment
        # --------------------------------------------------------------
        model.add_section(HeadingSection("SEG-Y Quality Control Report", level=1))
        model.add_section(
            TextSection(
                "Purpose",
                "This report documents automated and rule-based QC of SEG-Y structural integrity, headers, geometry, navigation, traces, amplitudes, noise, frequency content, timing/statics and—where data prerequisites are available—residual statics, velocity analysis, NMO, stack, migration, post-stack attributes and 4D repeatability.",
            )
        )

        severity_counts = self._severity_counts(finding_rows)
        status_counts = self._stage_status_counts(stages)
        unresolved = sum(not bool(item.get("is_resolved")) for item in finding_rows)
        critical_count = severity_counts.get("critical", 0) + severity_counts.get("error", 0)
        warning_count = severity_counts.get("warning", 0) + severity_counts.get("warn", 0)
        failed_stages = status_counts.get("fail", 0) + status_counts.get("error", 0)

        assessment = self._executive_assessment(
            str(overall_result).upper(),
            score,
            failed_stages,
            critical_count,
            warning_count,
            unresolved,
        )
        model.add_section(HeadingSection("Executive QC Assessment", level=2))
        model.add_section(TextSection("Automated assessment", assessment))
        model.add_section(
            TableSection(
                "Acceptance Summary",
                ["Item", "Result"],
                [
                    ["Overall result", str(overall_result).upper()],
                    ["Overall score", score if score is not None else "N/A"],
                    ["Passing stages", status_counts.get("pass", 0)],
                    ["Warning stages", status_counts.get("warn", 0)],
                    ["Failed/error stages", failed_stages],
                    ["Critical/error findings", critical_count],
                    ["Warning findings", warning_count],
                    ["Unresolved findings", unresolved],
                    ["Recommended disposition", self._recommended_disposition(str(overall_result), failed_stages, critical_count, warning_count)],
                ],
            )
        )

        # --------------------------------------------------------------
        # Run summary / inventory
        # --------------------------------------------------------------
        model.add_section(HeadingSection("Run Summary and Data Inventory", level=2))
        summary_rows = [
            ["Source file", str(source_path)],
            ["Run UUID", run_uuid],
            ["QC profile", profile],
            ["Profile version", run.get("profile_version") or summary.get("profile_version") or "Unknown"],
            ["Assigned to", run.get("assigned_to") or "Unassigned"],
            ["Run status", run.get("status") or summary.get("status") or "Unknown"],
            ["Overall result", str(overall_result).upper()],
            ["Overall score", score if score is not None else "N/A"],
            ["Trace count", self._first(summary, "trace_count", "traces", default="N/A")],
            ["Samples per trace", self._first(summary, "sample_count", "samples_per_trace", default="N/A")],
            ["Sample interval (µs)", self._first(summary, "sample_interval_us", "sample_interval", default="N/A")],
            ["Nominal sample interval (ms)", self._sample_interval_ms(summary)],
            ["Record length (ms)", self._record_length_ms(summary)],
            ["Inline count", self._first(summary, "inline_count", "inlines", default="N/A")],
            ["Crossline count", self._first(summary, "crossline_count", "crosslines", default="N/A")],
            ["CMP/CDP count", self._first(summary, "cmp_count", "cdp_count", default="N/A")],
            ["Coordinate system / CRS", self._first(summary, "crs", "coordinate_reference_system", default="N/A")],
            ["Coordinate units", self._first(summary, "coordinate_units", "coord_units", default="N/A")],
            ["Started", run.get("started_at") or summary.get("started_at") or "N/A"],
            ["Completed", run.get("completed_at") or summary.get("completed_at") or "N/A"],
            ["Duration (ms)", run.get("duration_ms") or summary.get("duration_ms") or "N/A"],
            ["Total findings", len(finding_rows)],
            ["Unresolved findings", unresolved],
        ]
        model.add_section(TableSection("Run Summary", ["Item", "Value"], summary_rows))

        # --------------------------------------------------------------
        # QC overview charts
        # --------------------------------------------------------------
        model.add_section(HeadingSection("QC Overview Charts", level=2))
        model.add_section(
            ChartSection(
                "Stage Status Distribution",
                chart_type="pie",
                data={
                    "labels": [key.title() for key in self.STATUS_ORDER],
                    "values": [status_counts.get(key, 0) for key in self.STATUS_ORDER],
                },
            )
        )
        model.add_section(
            ChartSection(
                "Findings by Severity",
                chart_type="pie",
                data={
                    "labels": [item.title() for item in self.SEVERITY_ORDER],
                    "values": [severity_counts.get(item, 0) for item in self.SEVERITY_ORDER],
                },
            )
        )

        stage_rows = self._stage_rows(stages, finding_rows)
        model.add_section(
            ChartSection(
                "Stage Scores",
                chart_type="horizontal_bar",
                data={
                    "labels": [str(row[1]) for row in stage_rows],
                    "values": [float(row[3]) if isinstance(row[3], (int, float)) else 0.0 for row in stage_rows],
                },
                x_label="QC Score (0-100)",
                y_label="QC Stage",
            )
        )
        model.add_section(
            ChartSection(
                "Stage Execution Duration",
                chart_type="horizontal_bar",
                data={
                    "labels": [str(row[1]) for row in stage_rows],
                    "values": [float(row[5]) if isinstance(row[5], (int, float)) else 0.0 for row in stage_rows],
                },
                x_label="Duration (ms)",
                y_label="QC Stage",
            )
        )
        model.add_section(
            ChartSection(
                "Findings by QC Stage",
                chart_type="horizontal_bar",
                data={
                    "labels": [str(row[1]) for row in stage_rows],
                    "values": [int(row[4]) if isinstance(row[4], (int, float)) else 0 for row in stage_rows],
                },
                x_label="Finding Count",
                y_label="QC Stage",
            )
        )

        # --------------------------------------------------------------
        # Stage results and grouped technical interpretation
        # --------------------------------------------------------------
        model.add_section(HeadingSection("Stage Results", level=2))
        model.add_section(
            TableSection(
                "Stage Results",
                ["Order", "Stage", "Result", "Score", "Findings", "Duration (ms)", "Message"],
                stage_rows,
            )
        )

        model.add_section(HeadingSection("QC Domain Summary", level=2))
        group_rows: list[list[Any]] = []
        for group_name, keywords in self.STAGE_GROUPS:
            group_stages = [stage for stage in stages if self._stage_matches(stage, keywords)]
            if not group_stages:
                continue
            group_status_counts = self._stage_status_counts(group_stages)
            scores = [self._stage_score(stage) for stage in group_stages]
            numeric_scores = [value for value in scores if isinstance(value, (int, float))]
            group_rows.append([
                group_name,
                len(group_stages),
                group_status_counts.get("pass", 0),
                group_status_counts.get("warn", 0),
                group_status_counts.get("fail", 0) + group_status_counts.get("error", 0),
                round(sum(numeric_scores) / len(numeric_scores), 1) if numeric_scores else "N/A",
                sum(self._stage_finding_count(stage, finding_rows) for stage in group_stages),
            ])
        model.add_section(
            TableSection(
                "QC Domain Summary",
                ["QC Domain", "Stages", "Pass", "Warn", "Fail/Error", "Mean Score", "Findings"],
                group_rows,
            )
        )
        if group_rows:
            model.add_section(
                ChartSection(
                    "Mean QC Score by Domain",
                    chart_type="horizontal_bar",
                    data={
                        "labels": [str(row[0]) for row in group_rows],
                        "values": [float(row[5]) if isinstance(row[5], (int, float)) else 0.0 for row in group_rows],
                    },
                    x_label="Mean QC Score (0-100)",
                    y_label="QC Domain",
                )
            )

        # Explicit processing-QC summary for the seven added stages.
        processing_keywords = ("residual_static", "velocity", "nmo", "stack", "migration", "attribute", "repeatability", "4d")
        processing_stages = [stage for stage in stages if self._stage_matches(stage, processing_keywords)]
        if processing_stages:
            model.add_section(HeadingSection("Advanced Seismic Processing QC", level=2))
            model.add_section(
                TextSection(
                    "Scope",
                    "This section summarizes residual statics, velocity, NMO, stack, migration, post-stack attribute and 4D/time-lapse QC where the source data and required contextual inputs were available. A SKIPPED result indicates that the technical prerequisite was not present and must not be interpreted as a pass or failure.",
                )
            )
            processing_rows = []
            for stage in processing_stages:
                metrics = self._stage_metrics(stage)
                processing_rows.append([
                    stage.get("stage_name") or stage.get("display_name") or stage.get("stage_key") or "Unknown",
                    str(stage.get("result") or stage.get("status") or "pending").upper(),
                    self._stage_score(stage),
                    self._stage_finding_count(stage, finding_rows),
                    self._metric_preview(metrics),
                    stage.get("message") or "",
                ])
            model.add_section(
                TableSection(
                    "Advanced Processing QC",
                    ["Stage", "Result", "Score", "Findings", "Key Metrics", "Summary"],
                    processing_rows,
                )
            )

        # --------------------------------------------------------------
        # Findings and corrective actions
        # --------------------------------------------------------------
        model.add_section(HeadingSection("QC Findings and Corrective Actions", level=2))
        if finding_rows:
            finding_table_rows = []
            for finding in finding_rows:
                finding_table_rows.append([
                    finding.get("id", ""),
                    str(finding.get("severity", "info")).upper(),
                    finding.get("stage_name") or finding.get("stage_key") or "",
                    finding.get("finding_code") or finding.get("code") or finding.get("rule_id") or "",
                    finding.get("title") or finding.get("message") or "",
                    finding.get("description") or finding.get("message") or "",
                    self._observed(finding),
                    self._expected(finding),
                    finding.get("trace_index") or self._context_trace(finding),
                    finding.get("suggested_action") or self._context_value(finding, "suggested_action") or "",
                    "Yes" if finding.get("is_resolved") else "No",
                    finding.get("resolution_note") or "",
                ])
            model.add_section(
                TableSection(
                    "QC Findings",
                    [
                        "ID", "Severity", "Stage", "Code", "Title", "Description", "Observed", "Expected",
                        "Trace / Location", "Suggested Action", "Resolved", "Resolution Note",
                    ],
                    finding_table_rows,
                )
            )
        else:
            model.add_section(TextSection("QC Findings", "No findings were recorded during this QC run."))

        recommendations = self._recommendations(finding_rows, str(overall_result))
        model.add_section(HeadingSection("Recommended Actions Before Final Acceptance", level=2))
        model.add_section(
            TableSection(
                "Recommended Actions",
                ["Priority", "Action"],
                [[index, action] for index, action in enumerate(recommendations, start=1)],
            )
        )

        # --------------------------------------------------------------
        # Detailed stage metrics
        # --------------------------------------------------------------
        model.add_section(HeadingSection("Detailed Stage Metrics", level=2))
        for stage in stages:
            metrics = self._stage_metrics(stage)
            if not metrics:
                continue
            title = stage.get("stage_name") or stage.get("display_name") or stage.get("stage_key") or "Stage"
            scalar_rows: list[list[Any]] = []
            structured_rows: list[list[Any]] = []
            for key, value in metrics.items():
                if key == "text":
                    continue
                if isinstance(value, (dict, list, tuple)):
                    structured_rows.append([self._humanize(key), json.dumps(value, ensure_ascii=False, default=str)])
                else:
                    scalar_rows.append([self._humanize(key), value])
            model.add_section(HeadingSection(str(title), level=3))
            if scalar_rows:
                model.add_section(TableSection(f"{title} — Scalar Metrics", ["Metric", "Value"], scalar_rows))
            if structured_rows:
                model.add_section(TableSection(f"{title} — Structured Metrics", ["Metric", "Value / JSON"], structured_rows))

        # --------------------------------------------------------------
        # Thresholds and audit information
        # --------------------------------------------------------------
        thresholds = parameters.get("thresholds") if isinstance(parameters.get("thresholds"), dict) else {}
        if not thresholds and isinstance(summary.get("thresholds"), dict):
            thresholds = summary.get("thresholds") or {}
        if thresholds:
            model.add_section(HeadingSection("QC Profile Thresholds", level=2))
            model.add_section(
                TableSection(
                    "QC Profile Thresholds",
                    ["Threshold", "Configured Value"],
                    [[self._humanize(key), value] for key, value in sorted(thresholds.items())],
                )
            )

        model.add_section(HeadingSection("Audit and Interpretation Notes", level=2))
        model.add_section(
            TableSection(
                "Audit Information",
                ["Item", "Value"],
                [
                    ["Generated at", datetime.now(timezone.utc).isoformat()],
                    ["Source file", str(source_path)],
                    ["Run UUID", run_uuid],
                    ["Profile", profile],
                    ["Total stages", len(stages)],
                    ["Total findings", len(finding_rows)],
                    ["Unresolved findings", unresolved],
                ],
            )
        )
        model.add_section(
            TextSection(
                "Interpretation note",
                "Automated QC findings are technical review aids. A high-amplitude, high-gradient, low-frequency, timing or repeatability anomaly may reflect valid subsurface geology, acquisition footprint, processing assumptions or data-quality problems. Final data acceptance and geological interpretation require review by a competent geophysicist using acquisition documentation, processing history and project objectives.",
            )
        )
        model.add_section(
            TextSection(
                "Report Footer",
                f"Generated by TGPAssure on {datetime.now(timezone.utc).isoformat()}. Findings must be reviewed before final data acceptance.",
                style="footer",
            )
        )
        return model

    # ------------------------------------------------------------------
    # Normalization and calculations
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_payload(
        payload_or_summary: Dict[str, Any],
        stage_results: Optional[List[Dict[str, Any]]],
        findings: Optional[List[Dict[str, Any]]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        if "run" in payload_or_summary:
            run = dict(payload_or_summary.get("run") or {})
            stages = list(payload_or_summary.get("stages") or [])
            finding_rows = list(payload_or_summary.get("findings") or [])
        else:
            run = dict(payload_or_summary)
            stages = list(stage_results or run.get("stages") or run.get("stage_outcomes") or [])
            finding_rows = list(findings or run.get("findings") or [])
        # Some active jobs place findings inside stage outcomes only.
        if not finding_rows:
            for stage in stages:
                for finding in stage.get("findings", []) or []:
                    item = dict(finding)
                    item.setdefault("stage_key", stage.get("stage_key"))
                    item.setdefault("stage_name", stage.get("stage_name") or stage.get("display_name"))
                    if "description" not in item and "message" in item:
                        item["description"] = item.get("message")
                    finding_rows.append(item)
        return run, stages, finding_rows

    def _stage_rows(self, stages: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for index, stage in enumerate(stages):
            order = stage.get("stage_order")
            if order is None:
                order = index
            rows.append([
                int(order) + 1,
                stage.get("stage_name") or stage.get("display_name") or stage.get("stage_key") or "Unknown",
                str(stage.get("result") or stage.get("status") or "pending").upper(),
                self._stage_score(stage),
                stage.get("finding_count", self._stage_finding_count(stage, findings)),
                stage.get("duration_ms") if stage.get("duration_ms") is not None else 0,
                stage.get("message") or "",
            ])
        return rows

    def _stage_score(self, stage: dict[str, Any]) -> Any:
        if stage.get("score") is not None:
            return stage.get("score")
        metrics = self._stage_metrics(stage)
        for key in ("score", "qc_score", "quality_score"):
            if metrics.get(key) is not None:
                return metrics.get(key)
        result = str(stage.get("result") or stage.get("status") or "").lower()
        if result == "pass":
            return 100.0
        if result == "warn":
            return 70.0
        if result in {"fail", "error"}:
            return 0.0
        return "N/A"

    def _stage_metrics(self, stage: dict[str, Any]) -> dict[str, Any]:
        metrics = stage.get("metrics")
        if isinstance(metrics, dict):
            return metrics
        return self._loads(stage.get("metrics_json"), {})

    @classmethod
    def _stage_status_counts(cls, stages: list[dict[str, Any]]) -> dict[str, int]:
        counts = {key: 0 for key in cls.STATUS_ORDER}
        for stage in stages:
            key = str(stage.get("result") or stage.get("status") or "pending").lower()
            counts[key] = counts.get(key, 0) + 1
        return counts

    @classmethod
    def _severity_counts(cls, findings: list[dict[str, Any]]) -> dict[str, int]:
        counts = {key: 0 for key in cls.SEVERITY_ORDER}
        for finding in findings:
            key = str(finding.get("severity", "info")).lower()
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _stage_matches(stage: dict[str, Any], keywords: tuple[str, ...]) -> bool:
        text = " ".join(
            str(stage.get(key, ""))
            for key in ("stage_key", "stage_name", "display_name")
        ).lower()
        return any(keyword in text for keyword in keywords)

    def _executive_assessment(
        self,
        overall_result: str,
        score: Any,
        failed_stages: int,
        critical_count: int,
        warning_count: int,
        unresolved: int,
    ) -> str:
        score_text = f"{float(score):.1f}/100" if isinstance(score, (int, float)) else str(score or "N/A")
        if overall_result in {"FAIL", "ERROR"} or failed_stages or critical_count:
            disposition = "The dataset should be held for corrective technical review before final release."
        elif overall_result == "WARN" or warning_count:
            disposition = "The dataset is conditionally acceptable subject to review and disposition of the reported warnings."
        else:
            disposition = "No material automated QC failure was detected; the dataset can proceed to final geophysical review."
        return (
            f"The SEG-Y QC run completed with an overall result of {overall_result} and a score of {score_text}. "
            f"There are {failed_stages} failed/error stages, {critical_count} critical/error findings, {warning_count} warning findings and {unresolved} unresolved findings. "
            f"{disposition}"
        )

    @staticmethod
    def _recommended_disposition(overall_result: str, failed_stages: int, critical_count: int, warning_count: int) -> str:
        result = str(overall_result).upper()
        if result in {"FAIL", "ERROR"} or failed_stages or critical_count:
            return "HOLD / CORRECT BEFORE ACCEPTANCE"
        if result == "WARN" or warning_count:
            return "CONDITIONAL ACCEPTANCE — REVIEW WARNINGS"
        return "ACCEPT SUBJECT TO FINAL GEOPHYSICIST SIGN-OFF"

    def _recommendations(self, findings: list[dict[str, Any]], overall_result: str) -> list[str]:
        actions: list[str] = []
        for finding in findings:
            action = finding.get("suggested_action") or self._context_value(finding, "suggested_action")
            action = str(action or "").strip()
            if action and action not in actions:
                actions.append(action)
            if len(actions) >= 15:
                break
        if not actions:
            if str(overall_result).upper() in {"FAIL", "ERROR"}:
                actions.append("Review all failed stages and correct the underlying SEG-Y, geometry, processing or metadata issue before release.")
            elif str(overall_result).upper() == "WARN":
                actions.append("Review warning findings and document whether each deviation is acceptable for the survey objective.")
            else:
                actions.append("Retain the QC report with the dataset and obtain final geophysicist sign-off before client delivery.")
        return actions

    @staticmethod
    def _metric_preview(metrics: dict[str, Any], limit: int = 5) -> str:
        if not isinstance(metrics, dict):
            return ""
        parts: list[str] = []
        for key, value in metrics.items():
            if isinstance(value, (dict, list, tuple)):
                continue
            parts.append(f"{SegyQcReportBuilder._humanize(key)}: {value}")
            if len(parts) >= limit:
                break
        return "; ".join(parts)

    @staticmethod
    def _sample_interval_ms(summary: dict[str, Any]) -> Any:
        value = summary.get("sample_interval_us")
        try:
            return round(float(value) / 1000.0, 6) if value is not None else "N/A"
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _record_length_ms(summary: dict[str, Any]) -> Any:
        samples = summary.get("sample_count", summary.get("samples_per_trace"))
        interval = summary.get("sample_interval_us")
        try:
            return round(float(samples) * float(interval) / 1000.0, 3)
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _first(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if mapping.get(key) is not None:
                return mapping.get(key)
        return default

    @staticmethod
    def _humanize(value: Any) -> str:
        return str(value).replace("_", " ").strip().title()

    @staticmethod
    def _loads(value: Any, fallback: Any) -> Any:
        try:
            return json.loads(value) if value else fallback
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _stage_finding_count(stage: Dict[str, Any], findings: List[Dict[str, Any]]) -> int:
        key = stage.get("stage_key")
        name = stage.get("stage_name") or stage.get("display_name")
        return sum(
            item.get("stage_key") == key
            or (name and (item.get("stage_name") == name or item.get("display_name") == name))
            for item in findings
        )

    @staticmethod
    def _context(finding: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(finding.get("context"), dict):
            return finding["context"]
        try:
            return json.loads(finding.get("context_json") or "{}")
        except (TypeError, ValueError):
            return {}

    @classmethod
    def _context_value(cls, finding: Dict[str, Any], key: str) -> Any:
        return cls._context(finding).get(key)

    @classmethod
    def _context_trace(cls, finding: Dict[str, Any]) -> str:
        traces = cls._context(finding).get("affected_trace_indices", [])
        if not traces:
            location = cls._context(finding).get("location_ref")
            return str(location or "")
        return ", ".join(str(value) for value in traces[:10]) + ("…" if len(traces) > 10 else "")

    @staticmethod
    def _observed(finding: Dict[str, Any]) -> str:
        value = finding.get("observed_value")
        if value is None:
            value = finding.get("value")
        return "" if value is None else f"{value} {finding.get('unit') or ''}".strip()

    @staticmethod
    def _expected(finding: Dict[str, Any]) -> str:
        minimum = finding.get("expected_min")
        maximum = finding.get("expected_max")
        threshold = finding.get("threshold")
        unit = finding.get("unit") or ""
        if minimum is not None and maximum is not None:
            return f"{minimum} to {maximum} {unit}".strip()
        if minimum is not None:
            return f">= {minimum} {unit}".strip()
        if maximum is not None:
            return f"<= {maximum} {unit}".strip()
        if threshold is not None:
            return f"Threshold: {threshold} {unit}".strip()
        return ""
