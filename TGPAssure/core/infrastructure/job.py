from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict, Callable
from enum import Enum, auto
import uuid
import threading

class JobStatus(Enum):
    QUEUED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()

class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

@dataclass
class JobSpec:
    job_type: str
    module: str
    priority: int = 0
    payload_json: str = '{}'

@dataclass
class JobHandle:
    job_id: int
    job_uuid: str
    job_type: str
    module: str
    status: JobStatus
    progress: float
    message: Optional[str] = None
    result_json: Optional[str] = None
    error_text: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

class Job(ABC):
    def __init__(self, job_spec: JobSpec) -> None:
        self.job_spec = job_spec
        self.job_uuid = str(uuid.uuid4())
        self._job_id: Optional[int] = None
        self._progress: float = 0.0
        self._progress_callback: Optional[Callable[[float], None]] = None

    @abstractmethod
    def run(self, context: Any, cancel_token: CancellationToken) -> Any:
        pass

    def get_job_type(self) -> str:
        return self.job_spec.job_type

    def get_module(self) -> str:
        return self.job_spec.module

    def get_priority(self) -> int:
        return self.job_spec.priority

    def get_payload(self) -> str:
        return self.job_spec.payload_json

    def set_job_id(self, job_id: int) -> None:
        self._job_id = job_id

    def get_job_id(self) -> Optional[int]:
        return self._job_id

    def get_job_uuid(self) -> str:
        return self.job_uuid

    def set_progress_callback(self, callback: Optional[Callable[[float], None]]) -> None:
        """Attach a manager-owned progress sink for background execution."""
        self._progress_callback = callback

    def update_progress(self, progress: float, *, notify: bool = True) -> None:
        self._progress = max(0.0, min(1.0, float(progress)))
        callback = self._progress_callback
        if notify and callback is not None:
            callback(self._progress)

    def get_progress(self) -> float:
        return self._progress
