from __future__ import annotations

import json
import mimetypes
import uuid
from typing import Any

from core.data_access.db_engine import DatabaseEngine
from modules.magnetic.exceptions import MagneticRepositoryError
from modules.magnetic.models import MagneticDataset, MagneticRunResult
from modules.magnetic.utils import safe_json


class MagneticRepository:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self.db_engine = db_engine
        self.ensure_schema()

    def ensure_schema(self) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS magnetic_datasets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_uuid TEXT NOT NULL UNIQUE,
                    file_id INTEGER,
                    source_path TEXT NOT NULL,
                    role TEXT NOT NULL,
                    survey_type TEXT NOT NULL,
                    instrument_make TEXT,
                    instrument_model TEXT,
                    sensor_serial_number TEXT,
                    crs TEXT,
                    coordinate_units TEXT,
                    magnetic_units TEXT,
                    record_count INTEGER NOT NULL,
                    line_count INTEGER NOT NULL DEFAULT 0,
                    start_time TEXT,
                    end_time TEXT,
                    min_x REAL, max_x REAL, min_y REAL, max_y REAL,
                    checksum TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    column_mapping_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS magnetic_line_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    line_id TEXT NOT NULL,
                    line_type TEXT,
                    station_count INTEGER,
                    length_m REAL,
                    azimuth_deg REAL,
                    mean_spacing_m REAL,
                    maximum_spacing_m REAL,
                    mean_field_nt REAL,
                    field_std_nt REAL,
                    noise_rms_nt REAL,
                    qc_status TEXT,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE CASCADE,
                    UNIQUE(dataset_id, line_id)
                );
                CREATE TABLE IF NOT EXISTS magnetic_base_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    station_name TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    sampling_interval_s REAL,
                    mean_field_nt REAL,
                    field_range_nt REAL,
                    noise_rms_nt REAL,
                    maximum_rate_nt_min REAL,
                    qc_status TEXT,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS magnetic_processing_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_uuid TEXT NOT NULL UNIQUE,
                    dataset_id INTEGER,
                    processing_run_id INTEGER,
                    product_type TEXT NOT NULL,
                    channel_name TEXT,
                    file_path TEXT,
                    parent_product_id INTEGER,
                    crs TEXT,
                    units TEXT,
                    cell_size REAL,
                    statistics_json TEXT NOT NULL DEFAULT '{}',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE SET NULL,
                    FOREIGN KEY(parent_product_id) REFERENCES magnetic_processing_products(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS magnetic_qc_masks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL,
                    qc_run_id INTEGER,
                    mask_name TEXT NOT NULL,
                    mask_path TEXT,
                    true_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE CASCADE,
                    FOREIGN KEY(qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def register_dataset(self, dataset: MagneticDataset) -> int:
        summary = dataset.summary()
        bounds = summary["bounds"]
        metadata = dataset.metadata
        conn = self.db_engine.get_write_connection()
        try:
            checksum = dataset.checksum
            existing = conn.execute("SELECT id FROM magnetic_datasets WHERE checksum = ? AND role = ?", (checksum, dataset.role.value)).fetchone()
            if existing:
                return int(existing[0])
            file_id = self._ensure_project_file(conn, dataset, checksum)
            cursor = conn.execute(
                """INSERT INTO magnetic_datasets (
                    dataset_uuid, file_id, source_path, role, survey_type, instrument_make, instrument_model,
                    sensor_serial_number, crs, coordinate_units, magnetic_units, record_count, line_count,
                    start_time, end_time, min_x, max_x, min_y, max_y, checksum, metadata_json, column_mapping_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), file_id, str(dataset.source_path), dataset.role.value, dataset.survey_type.value,
                    metadata.get("instrument_make"), metadata.get("instrument_model"), metadata.get("sensor_serial_number"),
                    dataset.crs, dataset.coordinate_units, dataset.magnetic_units, dataset.record_count, summary["line_count"],
                    summary["start_time"], summary["end_time"], bounds["min_x"], bounds["max_x"], bounds["min_y"], bounds["max_y"],
                    checksum, safe_json(metadata), safe_json(metadata.get("column_mapping", {})),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        except Exception as exc:
            conn.rollback()
            raise MagneticRepositoryError(f"Failed to register magnetic dataset: {exc}") from exc
        finally:
            conn.close()

    def save_run(self, result: MagneticRunResult, rover_dataset_id: int, line_statistics: dict[str, dict[str, Any]] | None = None) -> int:
        conn = self.db_engine.get_write_connection()
        try:
            dataset_row = conn.execute("SELECT file_id FROM magnetic_datasets WHERE id = ?", (rover_dataset_id,)).fetchone()
            file_id = int(dataset_row[0]) if dataset_row and dataset_row[0] is not None else None
            cursor = conn.execute(
                """INSERT INTO qc_runs (
                    project_id, file_id, run_uuid, module, qc_profile, profile_version, status,
                    overall_result, score, parameters_json, summary_json, started_at, completed_at, created_at
                ) VALUES (1, ?, ?, 'magnetic', ?, '1.0', ?, ?, ?, '{}', ?, ?, ?, CURRENT_TIMESTAMP)""",
                (file_id, result.run_uuid, result.profile_name, result.status.value, result.status.value, result.score, safe_json(result.summary), result.started_at, result.completed_at),
            )
            qc_run_id = int(cursor.lastrowid)
            for order, stage in enumerate(result.stage_outcomes, start=1):
                stage_cursor = conn.execute(
                    """INSERT INTO qc_stage_results (
                        qc_run_id, stage_key, stage_name, stage_order, status, result, score,
                        metrics_json, message, completed_at, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (qc_run_id, stage.stage_key, stage.display_name, order, stage.status.value, stage.status.value, self._stage_score(stage.status.value), safe_json(stage.metrics), stage.message, result.completed_at, stage.duration_ms),
                )
                stage_result_id = int(stage_cursor.lastrowid)
                for item in stage.findings:
                    metadata = json.loads(item.metadata_json or "{}")
                    conn.execute(
                        """INSERT INTO qc_findings (
                            qc_run_id, stage_result_id, finding_code, severity, category, title,
                            description, station_id, line_id, context_json, created_at
                        ) VALUES (?, ?, ?, ?, 'magnetic', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (qc_run_id, stage_result_id, item.rule_id, item.severity.value, item.rule_id, item.message, metadata.get("station_id"), metadata.get("line_id"), safe_json(metadata)),
                    )
            for line, metrics in (line_statistics or {}).items():
                conn.execute(
                    """INSERT OR REPLACE INTO magnetic_line_summaries (
                        dataset_id, line_id, line_type, station_count, length_m, azimuth_deg,
                        mean_spacing_m, maximum_spacing_m, noise_rms_nt, qc_status, metrics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rover_dataset_id, line, metrics.get("line_type"), metrics.get("record_count"), metrics.get("length_m"), metrics.get("azimuth_deg"), metrics.get("median_spacing_m"), metrics.get("maximum_spacing_m"), metrics.get("noise_rms_nt"), None, safe_json(metrics)),
                )
            conn.commit()
            return qc_run_id
        except Exception as exc:
            conn.rollback()
            raise MagneticRepositoryError(f"Failed to save magnetic QC run: {exc}") from exc
        finally:
            conn.close()


    @staticmethod
    def _ensure_project_file(conn, dataset: MagneticDataset, checksum: str) -> int | None:
        """Register the source in the shared project file inventory when available."""
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_files'"
        ).fetchone()
        if table is None:
            return None
        absolute_path = str(dataset.source_path.resolve()) if dataset.source_path.exists() else str(dataset.source_path)
        existing = conn.execute(
            "SELECT id FROM project_files WHERE project_id = 1 AND absolute_path = ?",
            (absolute_path,),
        ).fetchone()
        if existing:
            return int(existing[0])
        mime_type, _ = mimetypes.guess_type(dataset.source_path.name)
        size_bytes = dataset.source_path.stat().st_size if dataset.source_path.exists() else 0
        cursor = conn.execute(
            """INSERT INTO project_files (
                project_id, file_uuid, module, file_role, original_name, display_name,
                absolute_path, relative_path, extension, mime_type, size_bytes, sha256,
                status, metadata_json, imported_at
            ) VALUES (1, ?, 'magnetic', ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'available', ?, CURRENT_TIMESTAMP)""",
            (
                str(uuid.uuid4()), dataset.role.value, dataset.source_path.name, dataset.source_path.name,
                absolute_path, dataset.source_path.suffix.lower(), mime_type, size_bytes, checksum,
                safe_json(dataset.summary()),
            ),
        )
        return int(cursor.lastrowid)

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self.db_engine.get_read_connection()
        try:
            rows = conn.execute("SELECT run_uuid, qc_profile, status, overall_result, score, summary_json, created_at FROM qc_runs WHERE module = 'magnetic' ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _stage_score(status: str) -> float:
        return {"pass": 100.0, "warn": 65.0, "skipped": 80.0, "fail": 0.0}.get(status, 50.0)
