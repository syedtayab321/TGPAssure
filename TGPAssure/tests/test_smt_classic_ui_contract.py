from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _class_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def test_classic_smt_dialogs_cover_pdf_workflows() -> None:
    source = ROOT / "modules" / "seismic" / "smt" / "ui" / "dialogs.py"
    classes = _class_names(source)
    assert {
        "ProjectSelectionDialog",
        "ImportRecordsDialog",
        "ConfigurationDialog",
        "RecordsDialog",
        "ResultsDialog",
        "StatisticsDialog",
        "MaintenanceDialog",
        "PendingRetestsDialog",
        "SingleStringDialog",
        "TimeAnalysisDialog",
        "UnseenStringsDialog",
        "UtilitiesDialog",
    }.issubset(classes)
    text = source.read_text(encoding="utf-8")
    for label in (
        "New Or Select Project",
        "Select and Load SMT Files",
        "Test Limits and Parameters",
        "Histogram",
        "Scatter Plot",
        "Cross Plot",
        "Numerics",
        "Statistics",
        "Pending Retests",
        "Unseen Strings",
        "Single String Display",
        "Time Analysis",
        "DB Maintenance",
    ):
        assert label in text


def test_dashboard_keeps_ribbon_api_and_classic_launcher() -> None:
    source = ROOT / "modules" / "seismic" / "smt" / "ui" / "smt_dashboard.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    dashboard = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SmtDashboard")
    methods = {node.name for node in dashboard.body if isinstance(node, ast.FunctionDef)}
    assert {
        "new_select_project",
        "add_records",
        "configure",
        "show_records",
        "show_results",
        "show_statistics",
        "show_pending_retests",
        "show_single_string",
        "show_time_analysis",
        "show_unseen_strings",
        "show_maintenance",
        "export_records",
        "can_execute",
    }.issubset(methods)
    text = source.read_text(encoding="utf-8")
    for label in ("New/Select", "Add Records", "Configure", "Show Results", "Utilities", "Exit"):
        assert label in text
