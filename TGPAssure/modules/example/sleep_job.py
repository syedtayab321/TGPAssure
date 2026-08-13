# from __future__ import annotations

# import time
# from typing import Any

# from core.infrastructure.job import Job, JobSpec, CancellationToken
# from core.infrastructure.job_manager import JobManager

# class SleepJob(Job):
#     def __init__(self, sleep_seconds: float = 3.0) -> None:
#         spec = JobSpec(
#             job_type="sleep",
#             module="example",
#             priority=0,
#             payload_json=f'{{"sleep_seconds": {sleep_seconds}}}'
#         )
#         super().__init__(spec)
#         self.sleep_seconds = sleep_seconds
#         self._current_progress = 0.0

#     def run(self, context: Any, cancel_token: CancellationToken) -> dict[str, Any]:
#         steps = 4
#         for i in range(steps + 1):
#             if cancel_token.is_cancelled():
#                 return {"cancelled": True, "progress": self._current_progress}
#             progress = i / steps
#             self.update_progress(progress)
#             self._current_progress = progress
#             if context is not None and hasattr(context, 'update_progress'):
#                 context.update_progress(self.get_job_id(), progress)
#             if i < steps:
#                 time.sleep(self.sleep_seconds / steps)
#         return {
#             "completed": True,
#             "sleep_seconds": self.sleep_seconds,
#             "progress": self._current_progress
#         }

# class CancellableSleepJob(SleepJob):
#     def __init__(self, sleep_seconds: float = 5.0) -> None:
#         super().__init__(sleep_seconds)
#         self.job_spec.job_type = "cancellable_sleep"

#     def run(self, context: Any, cancel_token: CancellationToken) -> dict[str, Any]:
#         steps = 10
#         for i in range(steps + 1):
#             if cancel_token.is_cancelled():
#                 self.update_progress(self._current_progress)
#                 return {"cancelled": True, "progress": self._current_progress}
#             progress = i / steps
#             self.update_progress(progress)
#             self._current_progress = progress
#             if context is not None and hasattr(context, 'update_progress'):
#                 context.update_progress(self.get_job_id(), progress)
#             time.sleep(self.sleep_seconds / steps)
#         return {
#             "completed": True,
#             "sleep_seconds": self.sleep_seconds,
#             "progress": self._current_progress
#         }

# class FailingJob(Job):
#     def __init__(self) -> None:
#         spec = JobSpec(
#             job_type="failing",
#             module="example",
#             priority=0,
#             payload_json='{"error": "forced failure"}'
#         )
#         super().__init__(spec)

#     def run(self, context: Any, cancel_token: CancellationToken) -> Any:
#         self.update_progress(0.5)
#         if context is not None and hasattr(context, 'update_progress'):
#             context.update_progress(self.get_job_id(), 0.5)
#         raise RuntimeError("This job is designed to fail")