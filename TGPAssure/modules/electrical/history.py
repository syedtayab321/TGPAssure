from __future__ import annotations

from core.data_access.qc_history_repository import QcHistoryRepository
from core.data_access.db_engine import DatabaseEngine
from modules.electrical.models import ElectricalQcResult


def save_electrical_qc_run(db: DatabaseEngine, result: ElectricalQcResult) -> str:
    repository = QcHistoryRepository(db)
    return repository.record_run(
        module="electrical",
        file_path=result.dataset.source_path,
        profile=result.profile_name,
        status="completed",
        overall_result=result.status,
        score=result.score,
        summary=result.summary(),
        parameters={"method": result.dataset.method.value, "thresholds": result.thresholds},
        stages=[stage.to_history_dict(index) for index, stage in enumerate(result.stages, start=1)],
        findings=[finding.to_history_dict() for finding in result.findings],
        duration_ms=result.duration_ms,
    )
