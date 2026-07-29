from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LocalAuthStore:
    """Durable local login/payment cache for the desktop app.

    It stores the Firebase refresh token so a user remains signed in until an
    explicit logout.  The file is intentionally plain JSON for supportability;
    enterprise builds can replace this class with Windows Credential Manager or
    an OS keychain wrapper without changing the UI/service contract.
    """

    def __init__(self, app_data_dir: Path) -> None:
        self.app_data_dir = Path(app_data_dir)
        self.path = self.app_data_dir / "auth_state.json"
        self.app_data_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any] | None:
        try:
            if not self.path.is_file():
                return None
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def save(self, data: dict[str, Any]) -> None:
        payload = dict(data)
        payload["updated_at"] = utc_now_iso()
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="auth_state_", suffix=".json", dir=str(self.app_data_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass
