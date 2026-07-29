from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled", "development", "dev"}


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_dotenv(paths: Iterable[Path]) -> dict[str, str]:
    """Load a minimal .env file format without adding a dependency.

    Existing OS environment variables always win.  This makes packaged desktop
    builds safe for enterprise deployment where values may be injected by the
    launcher, system profile, or installer.
    """
    loaded: dict[str, str] = {}
    for path in paths:
        try:
            if not path.is_file():
                continue
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                value = _strip_quotes(value.split(" #", 1)[0].strip())
                loaded[key] = value
                os.environ.setdefault(key, value)
        except Exception:
            continue
    return loaded


@dataclass(frozen=True)
class AuthEnvironment:
    mode: str
    firebase_api_key: str
    firebase_project_id: str
    firestore_database: str
    stripe_checkout_url: str
    stripe_customer_portal_url: str
    stripe_success_url: str
    stripe_cancel_url: str
    dev_auto_login: bool
    dev_auto_approve: bool
    dev_name: str
    dev_email: str
    dev_password: str
    currency: str = "PKR"

    @property
    def is_development(self) -> bool:
        return self.mode in {"development", "dev", "local", "test", "testing"}

    @property
    def firebase_configured(self) -> bool:
        return bool(self.firebase_api_key and self.firebase_project_id)

    @property
    def stripe_configured(self) -> bool:
        return bool(self.stripe_checkout_url)

    @classmethod
    def load(cls, project_root: Path, app_data_dir: Path) -> "AuthEnvironment":
        load_dotenv(
            [
                project_root / ".env",
                project_root / ".env.local",
                app_data_dir / ".env",
            ]
        )
        mode = os.getenv("TGPA_ENV", os.getenv("APP_ENV", "production")).strip().lower() or "production"
        is_dev_default = mode in {"development", "dev", "local", "test", "testing"}
        return cls(
            mode=mode,
            firebase_api_key=os.getenv("FIREBASE_API_KEY", "").strip(),
            firebase_project_id=os.getenv("FIREBASE_PROJECT_ID", "").strip(),
            firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)").strip() or "(default)",
            stripe_checkout_url=os.getenv("TGPA_STRIPE_CHECKOUT_URL", "").strip(),
            stripe_customer_portal_url=os.getenv("TGPA_STRIPE_CUSTOMER_PORTAL_URL", "").strip(),
            stripe_success_url=os.getenv("TGPA_STRIPE_SUCCESS_URL", "https://checkout.stripe.com/success").strip(),
            stripe_cancel_url=os.getenv("TGPA_STRIPE_CANCEL_URL", "https://checkout.stripe.com/cancel").strip(),
            dev_auto_login=_parse_bool(os.getenv("TGPA_DEV_AUTO_LOGIN"), default=is_dev_default),
            dev_auto_approve=_parse_bool(os.getenv("TGPA_DEV_AUTO_APPROVE_PAYMENT"), default=is_dev_default),
            dev_name=os.getenv("TGPA_DEV_NAME", "TGP Development User").strip() or "TGP Development User",
            dev_email=os.getenv("TGPA_DEV_EMAIL", "developer@tgpassure.local").strip() or "developer@tgpassure.local",
            dev_password=os.getenv("TGPA_DEV_PASSWORD", "tgpassure-dev").strip() or "tgpassure-dev",
            currency=os.getenv("TGPA_CURRENCY", "PKR").strip().upper() or "PKR",
        )
