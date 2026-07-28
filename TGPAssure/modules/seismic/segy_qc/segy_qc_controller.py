from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.infrastructure.job_manager import JobManager
from modules.seismic.segy_qc.qc_profiles import SegyQcProfile, get_profile, list_profiles
from modules.seismic.segy_qc.qc_repository import SegyQcRepository
from modules.seismic.segy_qc.segy_qc_engine import STAGES, SegyQcJob, StageApprovalGate
from modules.seismic.segy_qc.segy_reader import SegyReader


class SegyQcController(QObject):
    file_loaded = Signal(dict)
    file_load_failed = Signal(str)
    stages_initialized = Signal(list)
    run_started = Signal(str, int)
    job_progress = Signal(int, float, str, float, str)
    stage_started = Signal(str, str, int)
    stage_completed = Signal(str, str, dict, list)
    stage_approval_required = Signal(str, str)
    run_completed = Signal(str, dict)
    run_failed = Signal(str, str)
    run_cancelled = Signal(str)
    run_loaded = Signal(str, dict, list, list)
    findings_changed = Signal(str)
    data_changed = Signal()

    def __init__(
        self,
        db_engine: DatabaseEngine,
        job_manager: JobManager,
        project_repo: ProjectRepository,
    ) -> None:
        super().__init__()
        self.db_engine = db_engine
        self.job_manager = job_manager
        self.project_repo = project_repo
        self.repository = SegyQcRepository(db_engine)
        self._file_path: Optional[Path] = None
        self._file_info: Dict[str, Any] = {}
        self._repeatability_base_path: Optional[Path] = None
        self._repeatability_base_info: Dict[str, Any] = {}
        self._current_run_uuid: Optional[str] = None
        self._current_job_id: Optional[int] = None
        self._job_runs: Dict[int, str] = {}
        self._approval_gate: Optional[StageApprovalGate] = None
        self._cancelled_runs_signalled: set[str] = set()

        self.job_manager.job_completed.connect(self._on_job_completed)
        self.job_manager.job_failed.connect(self._on_job_failed)
        self.job_manager.job_cancelled.connect(self._on_job_cancelled)

    @property
    def file_path(self) -> Optional[Path]:
        return self._file_path

    @property
    def repeatability_base_path(self) -> Optional[Path]:
        return self._repeatability_base_path

    @property
    def current_run_uuid(self) -> Optional[str]:
        return self._current_run_uuid

    @property
    def current_job_id(self) -> Optional[int]:
        return self._current_job_id

    def profile_descriptors(self) -> List[Dict[str, str]]:
        return [
            {
                "key": profile.key,
                "name": profile.name,
                "description": profile.description,
                "version": profile.version,
            }
            for profile in list_profiles()
        ]

    def get_effective_profile(self, profile_key: str) -> SegyQcProfile:
        overrides = self.repository.get_profile_overrides(profile_key)
        return get_profile(profile_key, overrides)

    def save_profile_overrides(self, profile_key: str, overrides: Dict[str, float]) -> SegyQcProfile:
        base = get_profile(profile_key)
        cleaned = {
            key: float(value)
            for key, value in overrides.items()
            if key in base.thresholds and float(value) != float(base.thresholds[key])
        }
        self.repository.save_profile_overrides(profile_key, cleaned)
        return self.get_effective_profile(profile_key)

    def set_file(self, file_path: str | Path) -> Dict[str, Any]:
        path = Path(file_path).expanduser().resolve()
        try:
            reader = SegyReader(path)
            info = reader.file_info()
            info["text_header"] = reader.text_header.text
            info["profile_ready"] = True
            self._file_path = path
            self._file_info = info
            if self._repeatability_base_path == path:
                self._repeatability_base_path = None
                self._repeatability_base_info = {}
            self.file_loaded.emit(info)
            return info
        except Exception as exc:
            self._file_path = None
            self._file_info = {}
            self.file_load_failed.emit(str(exc))
            raise

    def set_repeatability_base_file(self, file_path: str | Path | None) -> Dict[str, Any]:
        if not file_path:
            self._repeatability_base_path = None
            self._repeatability_base_info = {}
            return {}
        path = Path(file_path).expanduser().resolve()
        if self._file_path is not None and path == self._file_path:
            raise ValueError("The 4D base survey must be different from the current monitor SEG-Y file")
        reader = SegyReader(path)
        info = reader.file_info()
        info["text_header"] = reader.text_header.text
        self._repeatability_base_path = path
        self._repeatability_base_info = info
        return info

    def run_pipeline(
        self,
        profile_key: str = "standard",
        assigned_to: Optional[str] = None,
        require_stage_approval: bool = False,
    ) -> str:
        if self._file_path is None:
            raise ValueError("Select a valid SEG-Y file before running QC")
        if self._current_job_id is not None:
            handle = self.job_manager.get_job_status(self._current_job_id)
            if handle and handle.status.name in {"QUEUED", "RUNNING"}:
                raise RuntimeError("A SEG-Y QC job is already running")

        profile = self.get_effective_profile(profile_key)
        file_id = self.repository.ensure_file(self._file_path, self._file_info)
        parameters = {
            "profile_key": profile.key,
            "profile_name": profile.name,
            "profile_version": profile.version,
            "thresholds": profile.thresholds,
            "require_stage_approval": bool(require_stage_approval),
            "repeatability_base_path": str(self._repeatability_base_path) if self._repeatability_base_path else None,
            "repeatability_base_info": self._repeatability_base_info,
        }
        run_uuid = self.repository.create_run(
            file_id=file_id,
            file_path=self._file_path,
            profile_key=profile.key,
            profile_version=profile.version,
            parameters=parameters,
            assigned_to=assigned_to,
        )
        approval_gate = StageApprovalGate(bool(require_stage_approval))
        job = SegyQcJob(
            run_uuid=run_uuid,
            file_path=self._file_path,
            profile=profile,
            repository=self.repository,
            callbacks=self,
            approval_gate=approval_gate,
            repeatability_base_path=self._repeatability_base_path,
        )
        self.stages_initialized.emit(
            [{"key": key, "name": name, "order": order} for order, (key, name) in enumerate(STAGES)]
        )
        self._current_run_uuid = run_uuid
        self._approval_gate = approval_gate
        self._cancelled_runs_signalled.discard(run_uuid)
        job_id = self.job_manager.submit(job)
        self.repository.attach_job(run_uuid, job_id)
        self._current_job_id = job_id
        self._job_runs[job_id] = run_uuid
        self.run_started.emit(run_uuid, job_id)
        return run_uuid

    def cancel_current(self) -> bool:
        if self._approval_gate:
            self._approval_gate.cancel()
        if self._current_job_id is None:
            return False
        return self.job_manager.cancel(self._current_job_id)

    def approve_stage(self, stage_key: Optional[str] = None) -> None:
        if self._approval_gate:
            self._approval_gate.approve(stage_key)

    def assign_run(self, run_uuid: str, assignee: str) -> None:
        if not assignee.strip():
            raise ValueError("Assignee cannot be empty")
        self.repository.assign_run(run_uuid, assignee.strip())
        self.data_changed.emit()

    def list_runs(self, limit: int = 200, current_file_only: bool = False) -> List[Dict[str, Any]]:
        file_path = self._file_path if current_file_only else None
        return self.repository.list_runs(limit=limit, file_path=file_path)

    def load_run(self, run_uuid: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_uuid)
        if run is None:
            raise ValueError(f"QC run not found: {run_uuid}")
        stages = self.repository.get_stages(run_uuid)
        findings = self.repository.get_findings(run_uuid)
        self._current_run_uuid = run_uuid
        source_path = run.get("source_file_path") or run.get("file_absolute_path")
        if source_path and Path(source_path).exists():
            self._file_path = Path(source_path).resolve()
        self.run_loaded.emit(run_uuid, run, stages, findings)
        return {"run": run, "stages": stages, "findings": findings}

    def get_run(self, run_uuid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target = run_uuid or self._current_run_uuid
        return self.repository.get_run(target) if target else None

    def get_stage_results(self, run_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        target = run_uuid or self._current_run_uuid
        return self.repository.get_stages(target) if target else []

    def get_findings(
        self,
        run_uuid: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        target = run_uuid or self._current_run_uuid
        return self.repository.get_findings(target, severity=severity, resolved=resolved) if target else []

    def set_finding_resolution(self, finding_id: int, resolved: bool, note: str = "") -> None:
        self.repository.set_finding_resolution(finding_id, resolved, note)
        if self._current_run_uuid:
            self.findings_changed.emit(self._current_run_uuid)
        self.data_changed.emit()

    def register_report(
        self,
        run_uuid: str,
        format_name: str,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.repository.register_report(
            run_uuid=run_uuid,
            report_type="segy_qc",
            title=f"SEG-Y QC Report - {Path(file_path).stem}",
            format_name=format_name,
            file_path=file_path,
            metadata=metadata,
        )

    def report_payload(self, run_uuid: Optional[str] = None) -> Dict[str, Any]:
        target = run_uuid or self._current_run_uuid
        if not target:
            raise ValueError("No QC run is selected")
        run = self.repository.get_run(target)
        if run is None:
            raise ValueError(f"QC run not found: {target}")
        return {
            "run": run,
            "stages": self.repository.get_stages(target),
            "findings": self.repository.get_findings(target),
        }

    def qc_job_progress(
        self,
        job_id: int,
        overall: float,
        stage_key: str,
        stage_progress: float,
        message: str,
    ) -> None:
        if job_id:
            self.job_manager.update_progress(job_id, overall)
        self.job_progress.emit(job_id, overall, stage_key, stage_progress, message)

    def qc_stage_started(self, run_uuid: str, stage_key: str, stage_name: str, order: int) -> None:
        if run_uuid == self._current_run_uuid or self._current_run_uuid is None:
            self.stage_started.emit(stage_key, stage_name, order)

    def qc_stage_completed(self, run_uuid: str, outcome: Dict[str, Any]) -> None:
        if run_uuid == self._current_run_uuid:
            self.stage_completed.emit(
                outcome["key"],
                outcome["status"],
                outcome.get("metrics", {}),
                outcome.get("findings", []),
            )

    def qc_stage_approval_required(self, run_uuid: str, stage_key: str, stage_name: str) -> None:
        if run_uuid == self._current_run_uuid:
            self.stage_approval_required.emit(stage_key, stage_name)

    def qc_run_ready(self, run_uuid: str, summary: Dict[str, Any]) -> None:
        if run_uuid == self._current_run_uuid:
            self.run_completed.emit(run_uuid, summary)
            self.data_changed.emit()

    def qc_run_cancelled_from_worker(self, run_uuid: str) -> None:
        if run_uuid == self._current_run_uuid:
            self._emit_cancelled_once(run_uuid)
            self.data_changed.emit()

    def _emit_cancelled_once(self, run_uuid: str) -> None:
        if run_uuid in self._cancelled_runs_signalled:
            return
        self._cancelled_runs_signalled.add(run_uuid)
        self.run_cancelled.emit(run_uuid)

    def _on_job_completed(self, job_id: int, result: Any) -> None:
        if job_id not in self._job_runs:
            return
        run_uuid = self._job_runs.pop(job_id)
        if self._current_job_id == job_id:
            self._current_job_id = None
            self._approval_gate = None
        if isinstance(result, dict) and result.get("cancelled"):
            self._emit_cancelled_once(run_uuid)

    def _on_job_failed(self, job_id: int, error: str) -> None:
        run_uuid = self._job_runs.pop(job_id, None)
        if not run_uuid:
            return
        if self._current_job_id == job_id:
            self._current_job_id = None
            self._approval_gate = None
        self.run_failed.emit(run_uuid, error)
        self.data_changed.emit()

    def _on_job_cancelled(self, job_id: int) -> None:
        run_uuid = self._job_runs.pop(job_id, None)
        if not run_uuid:
            return
        if self._current_job_id == job_id:
            self._current_job_id = None
            self._approval_gate = None
        self._emit_cancelled_once(run_uuid)
        self.data_changed.emit()