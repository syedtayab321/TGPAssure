from __future__ import annotations

import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone
import logging
from typing import Optional

class CrashHandler:
    def __init__(self, log_dir: Optional[Path] = None) -> None:
        if log_dir is None:
            log_dir = Path.home() / ".tgpassure" / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._original_excepthook = sys.excepthook
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        self._original_excepthook = sys.excepthook
        sys.excepthook = self._handle_exception

    def uninstall(self) -> None:
        if not self._installed:
            return
        self._installed = False
        sys.excepthook = self._original_excepthook

    def _handle_exception(self, exc_type: type, exc_value: Exception, exc_tb: object) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        log_file = self.log_dir / f"crash_{timestamp}.log"
        formatted_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_content = f"=== Crash Report ===\n"
        log_content += f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        log_content += f"Exception Type: {exc_type.__name__}\n"
        log_content += f"Exception Message: {str(exc_value)}\n"
        log_content += f"Full Traceback:\n{formatted_traceback}\n"
        log_content += "=== End Report ===\n"
        try:
            log_file.write_text(log_content, encoding='utf-8')
        except Exception:
            pass
        logging.error("Unhandled exception occurred. Crash log written to: %s", log_file)
        logging.error(formatted_traceback)
        if self._original_excepthook is not None:
            self._original_excepthook(exc_type, exc_value, exc_tb)

    def get_logs(self) -> list[Path]:
        return sorted(self.log_dir.glob("crash_*.log"), reverse=True)

    def clear_logs(self) -> None:
        for log_file in self.log_dir.glob("crash_*.log"):
            try:
                log_file.unlink()
            except Exception:
                pass