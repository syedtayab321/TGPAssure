from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

from .models import (
    ImportOptions,
    ImportSummary,
    MEASUREMENT_FIELDS,
    SmtConfiguration,
    SmtTestRecord,
    evaluate_record,
)

_SCHEMA_VERSION = 1


def default_project_directory() -> Path:
    base = os.environ.get("TGPASSURE_DATA_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".tgpassure"
    path = root / "smt_projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_project_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(name).strip()).strip(" ._")
    return cleaned or "SMT_Project"


class SmtProjectDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()

    @classmethod
    def create(cls, directory: str | Path, name: str) -> "SmtProjectDatabase":
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{safe_project_name(name)}.sqlite"
        if path.exists():
            raise FileExistsError(path)
        database = cls(path)
        database.set_meta("project_name", safe_project_name(name))
        database.set_meta("created_at", datetime.now().isoformat(timespec="seconds"))
        database.save_configuration(SmtConfiguration.defaults(), recalculate=False)
        return database

    @staticmethod
    def list_projects(directory: str | Path | None = None) -> list[Path]:
        folder = Path(directory) if directory is not None else default_project_directory()
        folder.mkdir(parents=True, exist_ok=True)
        return sorted(folder.glob("*.sqlite"), key=lambda item: item.stat().st_mtime, reverse=True)

    def close(self) -> None:
        try:
            self.connection.commit()
        finally:
            self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS smt_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS smt_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                string_no TEXT NOT NULL DEFAULT '',
                serial TEXT NOT NULL DEFAULT '',
                tester TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                tested_at TEXT,
                original_tested_at TEXT NOT NULL DEFAULT '',
                date_corrected INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT 'SMT200',
                source_result TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'WARN',
                failure_flags TEXT NOT NULL DEFAULT '[]',
                noise REAL,
                resistance REAL,
                frequency REAL,
                damping REAL,
                sensitivity REAL,
                temperature REAL,
                distortion REAL,
                impedance REAL,
                polarity TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                source_hash TEXT NOT NULL DEFAULT '',
                source_row INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_smt_records_tested_at ON smt_records(tested_at);
            CREATE INDEX IF NOT EXISTS idx_smt_records_string ON smt_records(string_no);
            CREATE INDEX IF NOT EXISTS idx_smt_records_tester ON smt_records(tester);
            CREATE INDEX IF NOT EXISTS idx_smt_records_status ON smt_records(status);
            CREATE INDEX IF NOT EXISTS idx_smt_records_source ON smt_records(source_hash, source_row);
            CREATE TABLE IF NOT EXISTS smt_import_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                parsed_count INTEGER NOT NULL,
                inserted_count INTEGER NOT NULL,
                duplicate_count INTEGER NOT NULL,
                warning_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS smt_pending_exclusions (
                string_no TEXT PRIMARY KEY,
                reason TEXT NOT NULL DEFAULT '',
                excluded_at TEXT NOT NULL
            );
            """
        )
        self.set_meta("schema_version", str(_SCHEMA_VERSION))
        self.connection.commit()

    def set_meta(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO smt_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(key), str(value)),
        )
        self.connection.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.connection.execute("SELECT value FROM smt_meta WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    @property
    def project_name(self) -> str:
        return self.get_meta("project_name", self.path.stem)

    def load_configuration(self) -> SmtConfiguration:
        raw = self.get_meta("configuration", "")
        if not raw:
            return SmtConfiguration.defaults()
        try:
            return SmtConfiguration.from_dict(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return SmtConfiguration.defaults()

    def save_configuration(self, configuration: SmtConfiguration, *, recalculate: bool = True) -> None:
        self.set_meta("configuration", json.dumps(configuration.to_dict(), sort_keys=True))
        if recalculate:
            self.recalculate_statuses(configuration)

    def add_records(
        self,
        records: Sequence[SmtTestRecord],
        options: ImportOptions,
        configuration: SmtConfiguration | None = None,
    ) -> ImportSummary:
        config = configuration or self.load_configuration()
        summary = ImportSummary(parsed=len(records))
        imported_at = datetime.now().isoformat(timespec="seconds")
        by_file: dict[tuple[str, str], list[SmtTestRecord]] = defaultdict(list)
        for record in records:
            by_file[(record.source_file, record.source_hash)].append(record)
        with self.connection:
            for record in records:
                evaluation = evaluate_record(record, config)
                identity = (record.source_hash, int(record.source_row))
                existing = self.connection.execute(
                    "SELECT id FROM smt_records WHERE source_hash=? AND source_row=? LIMIT 1", identity
                ).fetchone()
                if existing is not None:
                    if options.duplicate_mode == "skip":
                        summary.duplicates += 1
                        continue
                    if options.duplicate_mode == "replace":
                        self.connection.execute("DELETE FROM smt_records WHERE id=?", (int(existing[0]),))
                        summary.replaced += 1
                self.connection.execute(
                    """
                    INSERT INTO smt_records(
                        string_no,serial,tester,operator,tested_at,original_tested_at,date_corrected,
                        model,source_result,status,failure_flags,noise,resistance,frequency,damping,
                        sensitivity,temperature,distortion,impedance,polarity,notes,source_file,
                        source_hash,source_row,imported_at,raw_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.string_no, record.serial, record.tester, record.operator,
                        record.tested_at.isoformat(timespec="seconds") if record.tested_at else None,
                        record.original_tested_at, int(record.date_corrected), record.model or "SMT200",
                        record.source_result, evaluation.status, json.dumps(evaluation.failure_flags),
                        record.noise, record.resistance, record.frequency, record.damping,
                        record.sensitivity, record.temperature, record.distortion, record.impedance,
                        record.polarity, record.notes, record.source_file, record.source_hash,
                        int(record.source_row), imported_at, json.dumps(record.raw, ensure_ascii=False, default=str),
                    ),
                )
                summary.inserted += 1
                summary.corrected_dates += int(record.date_corrected)
            for (source_file, source_hash), file_records in by_file.items():
                duplicates = sum(
                    1 for record in file_records
                    if self.connection.execute(
                        "SELECT COUNT(*) FROM smt_records WHERE source_hash=? AND source_row=?",
                        (record.source_hash, int(record.source_row)),
                    ).fetchone()[0] > 1
                )
                self.connection.execute(
                    """INSERT INTO smt_import_files(
                           source_file,source_hash,imported_at,parsed_count,inserted_count,duplicate_count,warning_count
                       ) VALUES(?,?,?,?,?,?,?)""",
                    (source_file, source_hash, imported_at, len(file_records), len(file_records) - duplicates, duplicates, 0),
                )
        return summary

    def recalculate_statuses(self, configuration: SmtConfiguration | None = None) -> int:
        config = configuration or self.load_configuration()
        rows = self.connection.execute("SELECT * FROM smt_records").fetchall()
        updates: list[tuple[str, str, int]] = []
        for row in rows:
            record = self._row_to_record(row)
            evaluation = evaluate_record(record, config)
            updates.append((evaluation.status, json.dumps(evaluation.failure_flags), int(row["id"])))
        with self.connection:
            self.connection.executemany(
                "UPDATE smt_records SET status=?, failure_flags=? WHERE id=?", updates
            )
        return len(updates)

    def query_records(
        self,
        *,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
        result: str = "all",
        tester: str = "",
        model: str = "",
        string_no: str = "",
        source_file: str = "",
        limit: int | None = None,
        ascending: bool = True,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("tested_at >= ?")
            params.append(_start_iso(start))
        if end is not None:
            clauses.append("tested_at <= ?")
            params.append(_end_iso(end))
        normalized_result = result.strip().upper()
        if normalized_result in {"PASS", "FAIL", "WARN"}:
            clauses.append("status = ?")
            params.append(normalized_result)
        elif normalized_result in {"BAD", "FAILURES"}:
            clauses.append("status = 'FAIL'")
        elif normalized_result in {"GOOD", "PASSED"}:
            clauses.append("status = 'PASS'")
        if tester:
            clauses.append("tester = ?")
            params.append(tester)
        if model:
            clauses.append("model = ?")
            params.append(model)
        if string_no:
            clauses.append("(string_no = ? OR serial = ?)")
            params.extend([string_no, string_no])
        if source_file:
            clauses.append("source_file = ?")
            params.append(source_file)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order = "ASC" if ascending else "DESC"
        sql = f"SELECT * FROM smt_records{where} ORDER BY COALESCE(tested_at, imported_at) {order}, id {order}"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))
        return [self._row_to_dict(row) for row in self.connection.execute(sql, params).fetchall()]

    def distinct_values(self, field_name: str) -> list[str]:
        allowed = {"tester", "model", "source_file", "string_no", "operator", "status"}
        if field_name not in allowed:
            raise ValueError(f"Unsupported field: {field_name}")
        rows = self.connection.execute(
            f"SELECT DISTINCT {field_name} FROM smt_records WHERE TRIM({field_name})<>'' ORDER BY {field_name}"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def record_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM smt_records").fetchone()[0])

    def statistics(
        self,
        *,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        rows = self.query_records(start=start, end=end)
        total = len(rows)
        strings = [str(row["string_no"] or row["serial"]).strip() for row in rows if str(row["string_no"] or row["serial"]).strip()]
        counts = Counter(strings)
        test_frequency = Counter(counts.values())
        statuses = Counter(str(row["status"]) for row in rows)
        failure_counts: Counter[str] = Counter()
        for row in rows:
            for flag in row.get("failure_flags", []):
                failure_counts[str(flag)] += 1
        source_failure_words = {"FAIL", "FAILED", "BAD", "NG", "REJECT", "REJECTED"}
        source_failures = sum(1 for row in rows if str(row.get("source_result") or "").strip().upper() in source_failure_words)
        source_fail_program_good = sum(
            1 for row in rows
            if str(row.get("source_result") or "").strip().upper() in source_failure_words and row["status"] == "PASS"
        )
        source_good_program_fail = sum(
            1 for row in rows
            if str(row.get("source_result") or "").strip().upper() not in source_failure_words and row["status"] == "FAIL"
        )
        numeric: dict[str, dict[str, float | int | None]] = {}
        numeric_good: dict[str, dict[str, float | int | None]] = {}
        for field_name in MEASUREMENT_FIELDS:
            values = [float(row[field_name]) for row in rows if row[field_name] is not None and math.isfinite(float(row[field_name]))]
            good_values = [float(row[field_name]) for row in rows if row["status"] == "PASS" and row[field_name] is not None and math.isfinite(float(row[field_name]))]
            numeric[field_name] = _describe(values)
            numeric_good[field_name] = _describe(good_values)
        return {
            "total_records": total,
            "total_unique_strings": len(counts),
            "total_failures": int(statuses.get("FAIL", 0)),
            "total_good": int(statuses.get("PASS", 0)),
            "total_warn": int(statuses.get("WARN", 0)),
            "source_failures": source_failures,
            "source_fail_program_good": source_fail_program_good,
            "source_good_program_fail": source_good_program_fail,
            "test_frequency": dict(sorted(test_frequency.items())),
            "failure_counts": dict(failure_counts),
            "numeric": numeric,
            "numeric_good": numeric_good,
            "tester_counts": dict(Counter(str(row["tester"] or "Unknown") for row in rows)),
            "model_counts": dict(Counter(str(row["model"] or "Unknown") for row in rows)),
            "start": _start_iso(start) if start is not None else "",
            "end": _end_iso(end) if end is not None else "",
        }

    def pending_retests(self, include_excluded: bool = False) -> list[dict[str, Any]]:
        where_exclusion = "" if include_excluded else "AND e.string_no IS NULL"
        sql = f"""
            WITH ranked AS (
                SELECT r.*, ROW_NUMBER() OVER (
                    PARTITION BY CASE WHEN TRIM(r.string_no)<>'' THEN r.string_no ELSE r.serial END
                    ORDER BY COALESCE(r.tested_at, r.imported_at) DESC, r.id DESC
                ) AS rn
                FROM smt_records r
                WHERE TRIM(r.string_no)<>'' OR TRIM(r.serial)<>''
            ), first_fail AS (
                SELECT CASE WHEN TRIM(string_no)<>'' THEN string_no ELSE serial END AS identity,
                       MIN(COALESCE(tested_at, imported_at)) AS first_failed_at
                FROM smt_records WHERE status='FAIL'
                GROUP BY CASE WHEN TRIM(string_no)<>'' THEN string_no ELSE serial END
            )
            SELECT ranked.*, first_fail.first_failed_at,
                   CASE WHEN e.string_no IS NULL THEN 0 ELSE 1 END AS excluded
            FROM ranked
            LEFT JOIN first_fail ON first_fail.identity = CASE WHEN TRIM(ranked.string_no)<>'' THEN ranked.string_no ELSE ranked.serial END
            LEFT JOIN smt_pending_exclusions e ON e.string_no = CASE WHEN TRIM(ranked.string_no)<>'' THEN ranked.string_no ELSE ranked.serial END
            WHERE ranked.rn=1 AND first_fail.first_failed_at IS NOT NULL AND ranked.status<>'PASS' {where_exclusion}
            ORDER BY COALESCE(ranked.tested_at, ranked.imported_at), ranked.string_no
        """
        return [self._row_to_dict(row) | {"first_failed_at": row["first_failed_at"], "excluded": bool(row["excluded"])} for row in self.connection.execute(sql).fetchall()]

    def exclude_pending(self, identities: Iterable[str], reason: str = "Removed from pending retest list") -> int:
        values = [(str(identity).strip(), reason, datetime.now().isoformat(timespec="seconds")) for identity in identities if str(identity).strip()]
        with self.connection:
            self.connection.executemany(
                "INSERT INTO smt_pending_exclusions(string_no,reason,excluded_at) VALUES(?,?,?) "
                "ON CONFLICT(string_no) DO UPDATE SET reason=excluded.reason, excluded_at=excluded.excluded_at",
                values,
            )
        return len(values)

    def restore_pending(self, identities: Iterable[str]) -> int:
        values = [(str(identity).strip(),) for identity in identities if str(identity).strip()]
        with self.connection:
            self.connection.executemany("DELETE FROM smt_pending_exclusions WHERE string_no=?", values)
        return len(values)

    def single_string_history(
        self,
        identities: Sequence[str],
        *,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        clean = [str(value).strip() for value in identities if str(value).strip()]
        if not clean:
            return []
        placeholders = ",".join("?" for _ in clean)
        clauses = [f"(string_no IN ({placeholders}) OR serial IN ({placeholders}))"]
        params: list[Any] = clean + clean
        if start is not None:
            clauses.append("tested_at >= ?")
            params.append(_start_iso(start))
        if end is not None:
            clauses.append("tested_at <= ?")
            params.append(_end_iso(end))
        sql = "SELECT * FROM smt_records WHERE " + " AND ".join(clauses) + " ORDER BY tested_at,id"
        return [self._row_to_dict(row) for row in self.connection.execute(sql, params).fetchall()]

    def time_analysis(
        self,
        measurement: str = "tests",
        *,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        if measurement != "tests" and measurement not in MEASUREMENT_FIELDS:
            raise ValueError(measurement)
        rows = self.query_records(start=start, end=end)
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            stamp = str(row.get("tested_at") or "")
            day = stamp[:10] if len(stamp) >= 10 else "Unknown"
            groups[day].append(row)
        output: list[dict[str, Any]] = []
        for day, members in sorted(groups.items()):
            entry: dict[str, Any] = {
                "date": day,
                "tests": len(members),
                "pass": sum(1 for row in members if row["status"] == "PASS"),
                "warn": sum(1 for row in members if row["status"] == "WARN"),
                "fail": sum(1 for row in members if row["status"] == "FAIL"),
                "unique_strings": len({row["string_no"] or row["serial"] for row in members}),
            }
            for field_name in MEASUREMENT_FIELDS:
                values = [float(row[field_name]) for row in members if row[field_name] is not None]
                entry[field_name] = mean(values) if values else None
            output.append(entry)
        return output

    def unseen_strings(self, since: date | datetime | str) -> list[dict[str, Any]]:
        configuration = self.load_configuration()
        cutoff = _start_iso(since)
        last_seen = {
            str(row["identity"]): row["last_seen"]
            for row in self.connection.execute(
                """SELECT CASE WHEN TRIM(string_no)<>'' THEN string_no ELSE serial END AS identity,
                          MAX(COALESCE(tested_at, imported_at)) AS last_seen
                   FROM smt_records
                   WHERE TRIM(string_no)<>'' OR TRIM(serial)<>''
                   GROUP BY CASE WHEN TRIM(string_no)<>'' THEN string_no ELSE serial END"""
            ).fetchall()
        }
        expected = self._expected_strings(configuration)
        output: list[dict[str, Any]] = []
        for identity in expected:
            stamp = last_seen.get(identity)
            if stamp is None or stamp < cutoff:
                output.append({"string_no": identity, "last_seen": stamp or "Never", "days_unseen": _days_since(stamp)})
        return output

    def missing_strings(self) -> list[str]:
        configuration = self.load_configuration()
        seen = {
            str(row[0]) for row in self.connection.execute(
                "SELECT DISTINCT CASE WHEN TRIM(string_no)<>'' THEN string_no ELSE serial END FROM smt_records"
            ).fetchall() if str(row[0]).strip()
        }
        return [identity for identity in self._expected_strings(configuration) if identity not in seen]

    def _expected_strings(self, configuration: SmtConfiguration) -> list[str]:
        start, end = int(configuration.string_min), int(configuration.string_max)
        if end >= start and end - start <= 200000:
            return [str(value) for value in range(start, end + 1)]
        return self.distinct_values("string_no")

    def maintenance_values(self, mode: str) -> list[str]:
        field = {
            "file": "source_file",
            "tester": "tester",
            "string": "string_no",
            "date": "substr(tested_at,1,10)",
            "model": "model",
            "result": "status",
        }.get(mode)
        if field is None:
            return []
        rows = self.connection.execute(
            f"SELECT DISTINCT {field} AS value FROM smt_records WHERE TRIM(COALESCE({field},''))<>'' ORDER BY value"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def maintenance_delete(self, mode: str, value: str = "") -> int:
        if mode == "duplicates":
            return self.remove_duplicates()
        field_sql = {
            "file": "source_file=?",
            "tester": "tester=?",
            "string": "(string_no=? OR serial=?)",
            "date": "substr(tested_at,1,10)=?",
            "model": "model=?",
            "result": "status=?",
        }.get(mode)
        if field_sql is None:
            raise ValueError(mode)
        params: tuple[Any, ...] = (value, value) if mode == "string" else (value,)
        with self.connection:
            cursor = self.connection.execute(f"DELETE FROM smt_records WHERE {field_sql}", params)
        return int(cursor.rowcount if cursor.rowcount >= 0 else 0)

    def remove_duplicates(self) -> int:
        before = self.record_count()
        with self.connection:
            self.connection.execute(
                """
                DELETE FROM smt_records
                WHERE id NOT IN (
                    SELECT MIN(id) FROM smt_records
                    GROUP BY string_no, serial, tester, tested_at, model,
                             noise, resistance, frequency, damping, sensitivity,
                             temperature, distortion, impedance, polarity
                )
                """
            )
        return before - self.record_count()

    def export_records_csv(self, path: str | Path, rows: Sequence[dict[str, Any]] | None = None) -> Path:
        import csv

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        data = list(rows) if rows is not None else self.query_records()
        fields = [
            "id", "status", "failure_flags", "string_no", "serial", "tester", "operator", "tested_at",
            "model", "noise", "resistance", "frequency", "damping", "sensitivity", "temperature",
            "distortion", "impedance", "polarity", "source_result", "notes", "source_file", "source_row",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in data:
                current = dict(row)
                current["failure_flags"] = "; ".join(current.get("failure_flags", []))
                writer.writerow(current)
        return output

    def _row_to_record(self, row: sqlite3.Row) -> SmtTestRecord:
        tested_at = None
        if row["tested_at"]:
            try:
                tested_at = datetime.fromisoformat(str(row["tested_at"]))
            except ValueError:
                tested_at = None
        return SmtTestRecord(
            string_no=str(row["string_no"] or ""), serial=str(row["serial"] or ""),
            tester=str(row["tester"] or ""), operator=str(row["operator"] or ""),
            tested_at=tested_at, original_tested_at=str(row["original_tested_at"] or ""),
            model=str(row["model"] or ""), source_result=str(row["source_result"] or ""),
            noise=row["noise"], resistance=row["resistance"], frequency=row["frequency"],
            damping=row["damping"], sensitivity=row["sensitivity"], temperature=row["temperature"],
            distortion=row["distortion"], impedance=row["impedance"], polarity=str(row["polarity"] or ""),
            notes=str(row["notes"] or ""), source_file=str(row["source_file"] or ""),
            source_hash=str(row["source_hash"] or ""), source_row=int(row["source_row"] or 0),
            date_corrected=bool(row["date_corrected"]),
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        raw_flags = result.get("failure_flags", "[]")
        try:
            result["failure_flags"] = list(json.loads(raw_flags))
        except (TypeError, ValueError, json.JSONDecodeError):
            result["failure_flags"] = []
        raw_json = result.get("raw_json", "{}")
        try:
            result["raw"] = dict(json.loads(raw_json))
        except (TypeError, ValueError, json.JSONDecodeError):
            result["raw"] = {}
        return result


def _start_iso(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat(timespec="seconds")
    text = str(value)
    return text if "T" in text or " " in text else text + "T00:00:00"


def _end_iso(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return datetime.combine(value, datetime.max.time()).isoformat(timespec="seconds")
    text = str(value)
    return text if "T" in text or " " in text else text + "T23:59:59"


def _describe(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "average": None, "std_dev": None, "skewness": None, "kurtosis": None, "maximum": None, "minimum": None}
    n = len(values)
    avg = mean(values)
    std = pstdev(values) if n > 1 else 0.0
    if std > 0 and n > 2:
        centered = [(value - avg) / std for value in values]
        skewness = sum(value ** 3 for value in centered) / n
        kurtosis = sum(value ** 4 for value in centered) / n - 3.0
    else:
        skewness = 0.0
        kurtosis = 0.0
    return {
        "count": n,
        "average": avg,
        "std_dev": std,
        "skewness": skewness,
        "kurtosis": kurtosis,
        "maximum": max(values),
        "minimum": min(values),
    }


def _days_since(stamp: str | None) -> int | None:
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return max(0, (datetime.now() - dt).days)
