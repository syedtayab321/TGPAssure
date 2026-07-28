from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Iterable

from core.domain.qc_engine import QCStatus
from core.infrastructure.job import CancellationToken, Job, JobSpec
from modules.gravity.context import GravityQcContext
from modules.gravity.gravity_repository import GravityRepository
from modules.gravity.models import GravityRunResult
from modules.gravity.qc_stages import (
    BaseDriftQC, BouguerTerrainQC, CoordinatesElevationQC, CrossoversQC, FileIntegrityQC,
    FinalAnomalyQC, FreeAirQC, LatitudeNormalGravityQC, LoopClosureQC, MetadataQC,
    ReductionAuditQC, RepeatabilityQC, SchemaUnitsQC, SummaryQC, TidalQC, TimeClockQC,
)

GRAVITY_QC_STAGES = (
    ("file_integrity", "File Integrity", FileIntegrityQC),
    ("schema_units", "Schema and Units", SchemaUnitsQC),
    ("metadata", "Survey Metadata", MetadataQC),
    ("time_clock", "Time and Clock", TimeClockQC),
    ("coordinates_elevation", "Coordinates and Elevation", CoordinatesElevationQC),
    ("base_drift", "Base Station and Drift", BaseDriftQC),
    ("tidal", "Tidal Correction", TidalQC),
    ("repeatability", "Repeat Stations", RepeatabilityQC),
    ("loop_closure", "Loop Closure", LoopClosureQC),
    ("latitude_normal_gravity", "Latitude / Normal Gravity", LatitudeNormalGravityQC),
    ("free_air", "Free-Air Correction", FreeAirQC),
    ("bouguer_terrain", "Bouguer and Terrain Corrections", BouguerTerrainQC),
    ("crossovers", "Cross-Over Consistency", CrossoversQC),
    ("reduction_audit", "Reduction Audit", ReductionAuditQC),
    ("final_anomaly", "Final Anomaly Consistency", FinalAnomalyQC),
    ("summary", "Final Gravity Summary", SummaryQC),
)
FIELD_STAGE_KEYS = tuple(key for key, _, _ in GRAVITY_QC_STAGES[:9]) + ("summary",)
FINAL_STAGE_KEYS = tuple(key for key, _, _ in GRAVITY_QC_STAGES[9:])


def _score(outcomes) -> float:
    relevant = [o for o in outcomes if o.stage_key != "summary"]
    if not relevant:
        return 0.0
    weights = {QCStatus.PASS: 1.0, QCStatus.WARN: 0.65, QCStatus.FAIL: 0.0, QCStatus.SKIPPED: 0.5}
    return round(100.0 * sum(weights.get(o.status, 0.0) for o in relevant) / len(relevant), 1)


class GravityQcPipeline:
    def __init__(self, repository: GravityRepository | None = None) -> None:
        self.repository = repository

    def run(
        self,
        context: GravityQcContext,
        *,
        selected_stage_keys: Iterable[str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> GravityRunResult:
        selected = set(selected_stage_keys) if selected_stage_keys else None
        definitions = [entry for entry in GRAVITY_QC_STAGES if selected is None or entry[0] in selected]
        if selected is not None and "summary" not in selected:
            definitions.append(next(e for e in GRAVITY_QC_STAGES if e[0] == "summary"))
        context.progress_callback = progress_callback
        context.cancellation_check = cancellation_check
        started = datetime.now(timezone.utc)
        outcomes = []
        for index, (key, name, stage_cls) in enumerate(definitions, 1):
            if context.cancelled():
                break
            context.report_progress(index - 1, len(definitions), f"Running {name}")
            outcome = stage_cls().run(context)
            outcomes.append(outcome)
            context.stage_outcomes[key] = outcome
            context.report_progress(index, len(definitions), f"Completed {name}")
        completed = datetime.now(timezone.utc)
        if context.cancelled():
            status = QCStatus.SKIPPED
        elif any(o.status == QCStatus.FAIL for o in outcomes if o.stage_key != "summary"):
            status = QCStatus.FAIL
        elif any(o.status == QCStatus.WARN for o in outcomes if o.stage_key != "summary"):
            status = QCStatus.WARN
        else:
            status = QCStatus.PASS
        result = GravityRunResult(
            run_uuid=str(uuid.uuid4()),
            profile_name=context.profile_name,
            status=status,
            score=_score(outcomes),
            stage_outcomes=outcomes,
            summary={
                "observations": context.observations.summary(),
                "base": context.base.summary() if context.base else None,
                "density_g_cm3": context.density_g_cm3,
                "base_statistics": context.stage_outcomes.get("base_drift").metrics if context.stage_outcomes.get("base_drift") else {},
                "repeat_statistics": {
                    "records": context.repeat_statistics,
                    **(context.stage_outcomes.get("repeatability").metrics if context.stage_outcomes.get("repeatability") else {}),
                },
                "loop_statistics": {
                    "records": context.loop_closures,
                    **(context.stage_outcomes.get("loop_closure").metrics if context.stage_outcomes.get("loop_closure") else {}),
                },
                "crossover_statistics": {
                    "records": context.crossovers,
                    **(context.stage_outcomes.get("crossovers").metrics if context.stage_outcomes.get("crossovers") else {}),
                },
                "reduction_statistics": {
                    **(context.stage_outcomes.get("free_air").metrics if context.stage_outcomes.get("free_air") else {}),
                    **(context.stage_outcomes.get("bouguer_terrain").metrics if context.stage_outcomes.get("bouguer_terrain") else {}),
                },
                "anomaly_statistics": context.stage_outcomes.get("final_anomaly").metrics if context.stage_outcomes.get("final_anomaly") else {},
                "loop_closures": context.loop_closures,
                "crossovers": context.crossovers,
                "processing_products": list(context.processing_products),
                "final_channels": list(context.observations.channel_names),
                "cancelled": context.cancelled(),
            },
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
        )
        if self.repository and not context.cancelled():
            dataset_id = self.repository.register_dataset(context.observations)
            if context.base:
                self.repository.register_dataset(context.base)
            self.repository.save_run(result, dataset_id)
        return result


class GravityQcJob(Job):
    def __init__(self, context: GravityQcContext, pipeline: GravityQcPipeline, selected_stage_keys=None,
                 progress_callback=None, stage_callback=None) -> None:
        super().__init__(JobSpec(job_type="gravity_qc", module="gravity"))
        self.context = context
        self.pipeline = pipeline
        self.selected_stage_keys = tuple(selected_stage_keys) if selected_stage_keys else None
        self.progress_callback = progress_callback
        self.stage_callback = stage_callback

    def run(self, _application_context, cancel_token: CancellationToken):
        def progress(current: int, total: int, message: str) -> None:
            self.update_progress(current / max(total, 1))
            if self.progress_callback:
                self.progress_callback(current, total, message)
            if self.stage_callback and message.startswith("Completed "):
                self.stage_callback(message.removeprefix("Completed "))
        return self.pipeline.run(
            self.context,
            selected_stage_keys=self.selected_stage_keys,
            progress_callback=progress,
            cancellation_check=cancel_token.is_cancelled,
        ).as_dict()
