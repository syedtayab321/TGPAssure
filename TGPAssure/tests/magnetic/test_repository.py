from __future__ import annotations

from pathlib import Path

from core.data_access.db_engine import DatabaseEngine
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.magnetic_engine import MagneticQcPipeline
from modules.magnetic.magnetic_profiles import get_profile
from modules.magnetic.magnetic_repository import MagneticRepository


def test_repository_persists_dataset_stages_and_findings(tmp_path, magnetic_datasets):
    database = DatabaseEngine(tmp_path / "magnetic.db")
    connection = database.get_write_connection()
    connection.executescript(Path("migrations/0001_initial.sql").read_text(encoding="utf-8"))
    connection.commit()
    connection.close()

    rover, base = magnetic_datasets
    profile = get_profile("field")
    context = MagneticQcContext(
        rover_dataset=rover,
        base_dataset=base,
        profile_name=profile.name,
        thresholds=profile.thresholds,
    )
    repository = MagneticRepository(database)
    result = MagneticQcPipeline(repository).run(context)

    connection = database.get_read_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM magnetic_datasets").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM qc_runs WHERE module='magnetic'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM qc_stage_results").fetchone()[0] == len(result.stage_outcomes)
        assert connection.execute("SELECT COUNT(*) FROM project_files WHERE module='magnetic'").fetchone()[0] == 2
    finally:
        connection.close()
