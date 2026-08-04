from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from modules.seismic.smt import ImportOptions, SmtConfiguration, SmtProjectDatabase, SmtTestRecord


def record(identity: str, when: datetime, resistance: float, row: int, result: str = "") -> SmtTestRecord:
    return SmtTestRecord(
        string_no=identity,
        tester="SMT-A",
        tested_at=when,
        model="SMT300",
        resistance=resistance,
        frequency=10.0,
        damping=0.60,
        distortion=0.02,
        source_result=result,
        source_file="daily.csv",
        source_hash="hash-1",
        source_row=row,
    )


def test_smt_database_queries_statistics_and_pending_retests(tmp_path: Path) -> None:
    db = SmtProjectDatabase.create(tmp_path, "Crew A")
    config = SmtConfiguration.defaults()
    config.string_min = 1
    config.string_max = 4
    config.limits["resistance"].minimum = 170.0
    config.limits["resistance"].maximum = 190.0
    db.save_configuration(config)
    now = datetime.now().replace(microsecond=0)
    rows = [
        record("1", now - timedelta(days=3), 220.0, 1, "FAIL"),
        record("2", now - timedelta(days=3), 220.0, 2, "FAIL"),
        record("2", now - timedelta(days=1), 180.0, 3, "PASS"),
        record("3", now - timedelta(days=2), 181.0, 4, "PASS"),
    ]
    summary = db.add_records(rows, ImportOptions())
    assert summary.inserted == 4
    assert db.record_count() == 4

    pending = db.pending_retests()
    assert [item["string_no"] for item in pending] == ["1"]
    stats = db.statistics()
    assert stats["total_records"] == 4
    assert stats["total_unique_strings"] == 3
    assert stats["total_failures"] == 2
    assert stats["source_failures"] == 2
    assert stats["test_frequency"][1] == 2
    assert stats["test_frequency"][2] == 1

    db.exclude_pending(["1"])
    assert db.pending_retests() == []
    assert db.pending_retests(include_excluded=True)[0]["excluded"] is True
    db.restore_pending(["1"])
    assert len(db.pending_retests()) == 1

    missing = db.missing_strings()
    assert missing == ["4"]
    unseen = db.unseen_strings(now.date())
    assert {item["string_no"] for item in unseen} == {"1", "2", "3", "4"}
    db.close()


def test_smt_database_duplicate_and_maintenance(tmp_path: Path) -> None:
    db = SmtProjectDatabase.create(tmp_path, "Maintenance")
    now = datetime.now().replace(microsecond=0)
    item = record("10", now, 180.0, 1)
    first = db.add_records([item], ImportOptions(duplicate_mode="skip"))
    second = db.add_records([item], ImportOptions(duplicate_mode="skip"))
    assert first.inserted == 1
    assert second.duplicates == 1
    assert db.record_count() == 1
    removed = db.maintenance_delete("tester", "SMT-A")
    assert removed == 1
    assert db.record_count() == 0
    db.close()


def test_smt_configuration_preserves_nominal_limits(tmp_path: Path) -> None:
    db = SmtProjectDatabase.create(tmp_path, "Nominal Limits")
    config = SmtConfiguration.defaults()
    assert config.limits["resistance"].nominal == 1757.0
    config.limits["frequency"].nominal = 10.05
    db.save_configuration(config, recalculate=False)
    loaded = db.load_configuration()
    assert loaded.limits["frequency"].nominal == 10.05
    assert loaded.limits["resistance"].minimum == 1713.0
    assert loaded.limits["resistance"].maximum == 1802.0
    db.close()
