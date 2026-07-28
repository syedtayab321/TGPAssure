from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QObject, Signal

from core.data_access.db_engine import DatabaseEngine
from core.infrastructure.job_manager import JobManager
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.magnetic_engine import MagneticQcJob, MagneticQcPipeline
from modules.magnetic.magnetic_profiles import get_profile
from modules.magnetic.magnetic_repository import MagneticRepository
from modules.magnetic.models import MagneticBoundary, MagneticDataset


class MagneticQcController(QObject):
    run_started = Signal(int)
    progress_changed = Signal(int, int, str)
    stage_completed = Signal(str)
    run_completed = Signal(dict)
    run_failed = Signal(str)
    run_cancelled = Signal()

    def __init__(self, db_engine: DatabaseEngine, job_manager: JobManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.job_manager = job_manager
        self.repository = MagneticRepository(db_engine)
        self.pipeline = MagneticQcPipeline(self.repository)
        self._active_job_id: int | None = None
        self._latest_context: MagneticQcContext | None = None
        job_manager.job_completed.connect(self._on_job_completed)
        job_manager.job_failed.connect(self._on_job_failed)
        job_manager.job_cancelled.connect(self._on_job_cancelled)

    @property
    def latest_context(self) -> MagneticQcContext | None:
        return self._latest_context

    def run_qc(
        self,
        rover: MagneticDataset,
        *,
        base: MagneticDataset | None = None,
        boundary: MagneticBoundary | None = None,
        profile_name: str = "standard",
        threshold_overrides: dict[str, Any] | None = None,
        selected_stage_keys: Iterable[str] | None = None,
        processing_products: dict[str, Any] | None = None,
    ) -> int:
        if self._active_job_id is not None:
            raise RuntimeError("A magnetic QC job is already running")
        profile = get_profile(profile_name, threshold_overrides)
        context = MagneticQcContext(
            rover_dataset=rover,
            base_dataset=base,
            survey_boundary=boundary,
            profile_name=profile.name,
            thresholds=profile.thresholds,
            processing_products=dict(processing_products or {}),
        )
        self._latest_context = context
        job = MagneticQcJob(
            context,
            self.pipeline,
            selected_stage_keys,
            progress_callback=lambda current, total, message: self.progress_changed.emit(current, total, message),
            stage_callback=self.stage_completed.emit,
        )
        job_id = self.job_manager.submit(job)
        self._active_job_id = job_id
        self.run_started.emit(job_id)
        return job_id

    def run_sync(self, context: MagneticQcContext, selected_stage_keys: Iterable[str] | None = None) -> dict[str, Any]:
        return self.pipeline.run(context, selected_stage_keys=selected_stage_keys).as_dict()

    @property
    def active_job_id(self) -> int | None:
        return self._active_job_id

    def cancel(self) -> bool:
        if self._active_job_id is None:
            return False
        return self.job_manager.cancel(self._active_job_id)

    def _on_job_completed(self, job_id: int, result: object) -> None:
        if job_id != self._active_job_id:
            return
        self._active_job_id = None
        if isinstance(result, dict):
            self.run_completed.emit(result)
        else:
            self.run_failed.emit("Magnetic QC returned an invalid result")

    def _on_job_failed(self, job_id: int, error: str) -> None:
        if job_id != self._active_job_id:
            return
        self._active_job_id = None
        self.run_failed.emit(error)

    def _on_job_cancelled(self, job_id: int) -> None:
        if job_id != self._active_job_id:
            return
        self._active_job_id = None
        self.run_cancelled.emit()
