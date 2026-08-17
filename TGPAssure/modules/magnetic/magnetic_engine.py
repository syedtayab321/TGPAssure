from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Iterable

from core.domain.qc_engine import QCStatus
from core.infrastructure.job import CancellationToken, Job, JobSpec
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.magnetic_repository import MagneticRepository
from modules.magnetic.models import MagneticRunResult
from modules.magnetic.qc_stages import (
    BaseStationQC, BoundaryQC, CoordinateQC, CorrectionAuditQC, CulturalNoiseQC,
    DiurnalQC, FileIntegrityQC, GradientQC, GridQC, LevelingQC, LineGeometryQC,
    MetadataQC, NoiseQC, PlatformQC, RepeatStationQC, SchemaQC, SensorQC,
    SpikeDropoutQC, StationSpacingQC, SummaryQC, TieLineQC, TimestampQC,
)
from modules.magnetic.utils import score_from_outcomes


MAGNETIC_QC_STAGES = (
    ("file_integrity", "File Integrity", FileIntegrityQC),
    ("schema", "Schema and Units", SchemaQC),
    ("metadata", "Survey Metadata", MetadataQC),
    ("timestamp", "Timestamp and Clock", TimestampQC),
    ("coordinate", "Coordinate and Navigation", CoordinateQC),
    ("boundary", "Survey Boundary", BoundaryQC),
    ("line_geometry", "Line Geometry", LineGeometryQC),
    ("station_spacing", "Station Spacing", StationSpacingQC),
    ("sensor", "Sensor Health", SensorQC),
    ("base_station", "Base Station", BaseStationQC),
    ("diurnal", "Diurnal Correction", DiurnalQC),
    ("spike_dropout", "Spikes and Dropouts", SpikeDropoutQC),
    ("noise", "Magnetic Noise", NoiseQC),
    ("gradient", "Magnetic Gradient", GradientQC),
    ("repeat_station", "Repeat Stations", RepeatStationQC),
    ("tie_line", "Tie-Line Misclosure", TieLineQC),
    ("platform", "Survey Platform", PlatformQC),
    ("cultural_noise", "Cultural Noise", CulturalNoiseQC),
    ("correction_audit", "Processing Audit", CorrectionAuditQC),
    ("leveling", "Line Leveling", LevelingQC),
    ("grid", "Magnetic Grid", GridQC),
    ("summary", "Final Magnetic Summary", SummaryQC),
)

RAW_STAGE_KEYS = tuple(key for key, _, _ in MAGNETIC_QC_STAGES[:18]) + ("summary",)
PROCESSED_STAGE_KEYS = ("diurnal", "noise", "repeat_station", "tie_line", "correction_audit", "leveling", "grid", "summary")


class MagneticQcPipeline:
    def __init__(self, repository: MagneticRepository | None = None) -> None:
        self.repository = repository

    def run(
        self,
        context: MagneticQcContext,
        *,
        selected_stage_keys: Iterable[str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
        stop_on_failure: bool = False,
    ) -> MagneticRunResult:
        selected = set(selected_stage_keys) if selected_stage_keys else None
        definitions = [entry for entry in MAGNETIC_QC_STAGES if selected is None or entry[0] in selected]
        if selected is not None and "summary" not in selected:
            definitions.append(next(entry for entry in MAGNETIC_QC_STAGES if entry[0] == "summary"))
        context.progress_callback = progress_callback
        context.cancellation_check = cancellation_check
        started = datetime.now(timezone.utc)
        outcomes = []
        stopped_on_failure = False
        for index, (key, display_name, stage_class) in enumerate(definitions, start=1):
            if context.cancelled():
                break
            context.report_progress(index - 1, len(definitions), f"Running {display_name}")
            outcome = stage_class().run(context)
            outcomes.append(outcome)
            context.stage_outcomes[key] = outcome
            context.report_progress(index, len(definitions), f"Completed {display_name}")
            if stop_on_failure and outcome.status == QCStatus.FAIL and key != "summary":
                stopped_on_failure = True
                break
        # A stop-on-failure run still produces the standard consolidated summary
        # for auditability, but does not execute any remaining scientific stages.
        summary_requested = any(key == "summary" for key, _name, _stage in definitions)
        summary_completed = any(outcome.stage_key == "summary" for outcome in outcomes)
        if stopped_on_failure and summary_requested and not summary_completed and not context.cancelled():
            key, display_name, stage_class = next(entry for entry in MAGNETIC_QC_STAGES if entry[0] == "summary")
            context.report_progress(len(outcomes), max(len(outcomes) + 1, 1), f"Running {display_name}")
            outcome = stage_class().run(context)
            outcomes.append(outcome)
            context.stage_outcomes[key] = outcome
            context.report_progress(len(outcomes), len(outcomes), f"Completed {display_name}")
        completed = datetime.now(timezone.utc)
        if context.cancelled():
            status = QCStatus.SKIPPED
        elif outcomes and outcomes[-1].stage_key == "summary":
            status = outcomes[-1].status
        elif any(stage.status == QCStatus.FAIL for stage in outcomes):
            status = QCStatus.FAIL
        elif any(stage.status == QCStatus.WARN for stage in outcomes):
            status = QCStatus.WARN
        else:
            status = QCStatus.PASS
        score = score_from_outcomes(stage.status for stage in outcomes if stage.stage_key != "summary")
        result = MagneticRunResult(
            run_uuid=str(uuid.uuid4()), profile_name=context.profile_name, status=status,
            score=score, stage_outcomes=outcomes,
            summary={
                "rover": context.rover_dataset.summary(),
                "base": context.base_dataset.summary() if context.base_dataset else None,
                "line_statistics": context.line_statistics,
                "base_statistics": context.base_statistics,
                "processing_products": list(context.processing_products.keys()),
                "cancelled": context.cancelled(),
            },
            started_at=started.isoformat(), completed_at=completed.isoformat(),
        )
        if self.repository and not context.cancelled():
            dataset_id = self.repository.register_dataset(context.rover_dataset)
            if context.base_dataset:
                self.repository.register_dataset(context.base_dataset)
            self.repository.save_run(result, dataset_id, context.line_statistics)
        return result


class MagneticQcJob(Job):
    def __init__(
        self,
        context: MagneticQcContext,
        pipeline: MagneticQcPipeline,
        selected_stage_keys: Iterable[str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        stage_callback: Callable[[str], None] | None = None,
        stop_on_failure: bool = False,
    ) -> None:
        super().__init__(JobSpec(job_type="magnetic_qc", module="magnetic"))
        self.context = context
        self.pipeline = pipeline
        self.selected_stage_keys = tuple(selected_stage_keys) if selected_stage_keys else None
        self.progress_callback = progress_callback
        self.stage_callback = stage_callback
        self.stop_on_failure = bool(stop_on_failure)

    def run(self, _application_context, cancel_token: CancellationToken):
        def progress(current: int, total: int, message: str) -> None:
            self.update_progress(current / max(total, 1))
            if self.progress_callback:
                self.progress_callback(current, total, message)
            if self.stage_callback and message.startswith("Completed "):
                self.stage_callback(message.removeprefix("Completed "))
        result = self.pipeline.run(
            self.context,
            selected_stage_keys=self.selected_stage_keys,
            progress_callback=progress,
            cancellation_check=cancel_token.is_cancelled,
            stop_on_failure=self.stop_on_failure,
        )
        return result.as_dict()
