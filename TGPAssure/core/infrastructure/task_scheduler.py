from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional


class ScheduledTask:
    def __init__(self, task_id: str, func: Callable[..., None], delay: float, args=(), kwargs=None):
        self.task_id = task_id
        self.func = func
        self.delay = delay
        self.args = args
        self.kwargs = kwargs or {}
        self._timer: Optional[threading.Timer] = None

    def start(self) -> None:
        self._timer = threading.Timer(self.delay, self.func, args=self.args, kwargs=self.kwargs)
        self._timer.start()

    def cancel(self) -> None:
        if self._timer:
            self._timer.cancel()


class TaskScheduler:
    """Simple in-process task scheduler.

    This scheduler is intentionally minimal: it schedules callables to run after
    a given delay and keeps a registry so tasks can be cancelled. It is suitable
    for UI-driven scheduling (delayed retries, polling, housekeeping).
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, ScheduledTask] = {}
        self._lock = threading.RLock()

    def schedule(self, task_id: str, func: Callable[..., None], delay: float, *args, **kwargs) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].cancel()
            st = ScheduledTask(task_id, func, delay, args=args, kwargs=kwargs)
            self._tasks[task_id] = st
            st.start()

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].cancel()
                del self._tasks[task_id]
                return True
            return False

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._tasks.keys())
            for tid in ids:
                try:
                    self._tasks[tid].cancel()
                except Exception:
                    pass
                del self._tasks[tid]
