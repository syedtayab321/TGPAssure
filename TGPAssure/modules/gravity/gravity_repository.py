from __future__ import annotations

import json
import uuid
from typing import Any

from core.data_access.db_engine import DatabaseEngine
from modules.gravity.models import GravityDataset, GravityRunResult


class GravityRepository:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self.db_engine = db_engine
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS gravity_datasets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_uuid TEXT NOT NULL UNIQUE,
                    file_id INTEGER,
                    source_path TEXT NOT NULL,
                    role TEXT NOT NULL,
                    survey_type TEXT NOT NULL,
                    instrument_make TEXT,
                    instrument_model TEXT,
                    instrument_serial TEXT,
                    crs TEXT,
                    gravity_units TEXT,
                    elevation_units TEXT,
                    record_count INTEGER NOT NULL,
                    station_count INTEGER NOT NULL DEFAULT 0,
                    line_count INTEGER NOT NULL DEFAULT 0,
                    start_time TEXT,
                    end_time TEXT,
                    checksum TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_gravity_dataset_checksum ON gravity_datasets(checksum);
                CREATE TABLE IF NOT EXISTS gravity_processing_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_uuid TEXT NOT NULL UNIQUE,
                    dataset_id INTEGER,
                    processing_run_id INTEGER,
                    product_type TEXT NOT NULL,
                    channel_name TEXT,
                    file_path TEXT,
                    crs TEXT,
                    units TEXT,
                    statistics_json TEXT NOT NULL DEFAULT '{}',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def register_dataset(self, dataset: GravityDataset) -> int:
        summary = dataset.summary()
        conn = self.db_engine.get_write_connection()
        try:
            existing = conn.execute("SELECT id FROM gravity_datasets WHERE checksum = ?", (dataset.checksum,)).fetchone()
            if existing:
                return int(existing["id"])
            cursor = conn.execute(
                """INSERT INTO gravity_datasets
                (dataset_uuid, source_path, role, survey_type, crs, gravity_units, elevation_units,
                 record_count, station_count, line_count, start_time, end_time, checksum, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), str(dataset.source_path), dataset.role.value, dataset.survey_type.value,
                    dataset.crs, dataset.gravity_units, dataset.elevation_units, dataset.record_count,
                    dataset.station_count, dataset.line_count, summary.get("start_time"), summary.get("end_time"),
                    dataset.checksum, json.dumps(dataset.metadata, default=str),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def save_run(self, result: GravityRunResult, dataset_id: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            # General QC history tables may not exist in isolated unit-test databases.
            table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='qc_runs'").fetchone()
            if not table:
                return
            cursor = conn.execute(
                """INSERT INTO qc_runs
                (run_uuid, module, qc_profile, status, overall_result, score, parameters_json, summary_json, started_at, completed_at)
                VALUES (?, 'gravity', ?, ?, ?, ?, '{}', ?, ?, ?)""",
                (result.run_uuid, result.profile_name, "completed", result.status.value, result.score,
                 json.dumps(result.summary, default=str), result.started_at, result.completed_at),
            )
            run_id = int(cursor.lastrowid)
            for order, stage in enumerate(result.stage_outcomes):
                s = conn.execute(
                    """INSERT INTO qc_stage_results
                    (qc_run_id, stage_key, stage_name, stage_order, status, result, score, metrics_json, message, duration_ms, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (run_id, stage.stage_key, stage.display_name, order, stage.status.value, stage.status.value,
                     None, json.dumps(stage.metrics, default=str), stage.message, stage.duration_ms),
                )
                stage_id = int(s.lastrowid)
                for finding in stage.findings:
                    conn.execute(
                        """INSERT INTO qc_findings
                        (qc_run_id, stage_result_id, finding_code, severity, category, title, description,
                         context_json, created_at)
                        VALUES (?, ?, ?, ?, 'gravity', ?, ?, ?, datetime('now'))""",
                        (run_id, stage_id, finding.rule_id, finding.severity.value, finding.rule_id.replace('_',' ').title(),
                         finding.message, finding.metadata_json or "{}"),
                    )
            conn.commit()
        finally:
            conn.close()
