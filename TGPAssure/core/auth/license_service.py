from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.auth.env import AuthEnvironment
from core.auth.firebase_client import AuthError, FirebaseClient, NetworkUnavailable
from core.auth.local_store import LocalAuthStore, utc_now_iso
from core.auth.plans import (
    ALL_FEATURE_KEYS,
    FEATURE_BY_KEY,
    FREE_FEATURES,
    PLAN_BY_KEY,
    feature_for_action,
    feature_for_provider,
    features_for_plan,
    module_for_feature,
    module_summary,
    monthly_total_for_features,
)


@dataclass(frozen=True)
class AuthUser:
    uid: str
    name: str
    email: str


class LicenseService:
    def __init__(self, app_data_dir: Path, env: AuthEnvironment) -> None:
        self.app_data_dir = Path(app_data_dir)
        self.env = env
        self.local_store = LocalAuthStore(app_data_dir)
        self.firebase = FirebaseClient(env)
        self._state: dict[str, Any] = {}
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def is_authenticated(self) -> bool:
        user = self._state.get("user")
        return bool(isinstance(user, dict) and user.get("uid") and user.get("email"))

    @property
    def user(self) -> AuthUser | None:
        user = self._state.get("user") if isinstance(self._state, dict) else None
        if not isinstance(user, dict):
            return None
        return AuthUser(str(user.get("uid") or ""), str(user.get("name") or ""), str(user.get("email") or ""))

    @property
    def current_plan(self) -> str:
        return str(self._state.get("license", {}).get("plan") or "free")

    @property
    def entitlement_features(self) -> set[str]:
        license_info = self._state.get("license", {}) if isinstance(self._state, dict) else {}
        features = license_info.get("features", []) if isinstance(license_info, dict) else []
        return {key for key in features if key in FEATURE_BY_KEY}

    @property
    def is_development(self) -> bool:
        return self.env.is_development

    def try_auto_login(self) -> bool:
        if self.env.is_development and self.env.dev_auto_login:
            self._state = self._development_state(
                plan="enterprise_all",
                features=ALL_FEATURE_KEYS,
                payment_note="development-auto-login",
            )
            self.local_store.save(self._state)
            return True

        local = self.local_store.load()
        if not local:
            return False
        self._state = local
        refresh_token = str(local.get("refresh_token") or "")
        if self.env.firebase_configured and refresh_token:
            try:
                refreshed = self.firebase.refresh(refresh_token)
                self._state["id_token"] = refreshed.get("id_token") or refreshed.get("idToken") or local.get("id_token")
                self._state["refresh_token"] = refreshed.get("refresh_token") or refresh_token
                self._state["expires_at"] = time.time() + int(refreshed.get("expires_in") or 3600) - 60
                self.sync_from_firebase(silent=True)
                self.local_store.save(self._state)
            except NetworkUnavailable as exc:
                self._last_error = str(exc)
            except AuthError as exc:
                self._last_error = str(exc)
                return False
        return self.is_authenticated

    def login(self, email: str, password: str) -> None:
        if not self.env.firebase_configured:
            if self.env.is_development:
                self._state = self._development_state(plan="free", features=FREE_FEATURES, email=email)
                self.local_store.save(self._state)
                return
            raise AuthError("Firebase is not configured. Add FIREBASE_API_KEY and FIREBASE_PROJECT_ID in .env.")
        result = self.firebase.sign_in(email.strip(), password)
        self._adopt_firebase_auth_result(result, name="")
        self.sync_from_firebase(silent=True, create_if_missing=True)
        self.local_store.save(self._state)

    def register(self, name: str, email: str, password: str) -> None:
        if not self.env.firebase_configured:
            if self.env.is_development:
                self._state = self._development_state(plan="free", features=FREE_FEATURES, name=name, email=email)
                self.local_store.save(self._state)
                return
            raise AuthError("Internet and Firebase configuration are required for account creation.")
        result = self.firebase.create_user(name.strip(), email.strip(), password)
        self._adopt_firebase_auth_result(result, name=name.strip())
        self._write_profile(self._profile_payload(plan="free", features=FREE_FEATURES, source="account-created"))
        self.local_store.save(self._state)

    def logout(self) -> None:
        self._state = {}
        self.local_store.clear()

    def refresh_or_use_cache(self) -> bool:
        return self.try_auto_login() if not self.is_authenticated else True

    def has_feature(self, feature_key: str | None) -> bool:
        if not feature_key:
            return True
        if self.env.is_development and self.env.dev_auto_login:
            return True
        return feature_key in self.entitlement_features

    def has_provider(self, provider_id: str | None) -> bool:
        return self.has_feature(feature_for_provider(provider_id))

    def has_action(self, action_id: str | None) -> bool:
        return self.has_feature(feature_for_action(action_id))

    def has_module(self, module_key: str | None) -> bool:
        if not module_key or module_key == "home":
            return True
        return any(module_for_feature(feature) == module_key for feature in self.entitlement_features)

    def feature_for_provider(self, provider_id: str | None) -> str | None:
        return feature_for_provider(provider_id)

    def feature_for_action(self, action_id: str | None) -> str | None:
        return feature_for_action(action_id)

    def describe_license(self) -> dict[str, Any]:
        license_info = self._state.get("license", {}) if isinstance(self._state, dict) else {}
        payments = self._state.get("payments", []) if isinstance(self._state, dict) else []
        return {
            "plan": self.current_plan,
            "features": sorted(self.entitlement_features),
            "modules": module_summary(self.entitlement_features),
            "payments": payments if isinstance(payments, list) else [],
            "license": license_info if isinstance(license_info, dict) else {},
        }

    def create_checkout(self, plan_key: str, selected_features: Iterable[str]) -> str:
        if not self.is_authenticated or self.user is None:
            raise AuthError("Login is required before payment.")
        plan = PLAN_BY_KEY.get(plan_key)
        if plan is None:
            raise AuthError("Invalid subscription plan.")
        selected = sorted(features_for_plan(plan_key, selected_features))
        amount = plan.monthly_pkr if plan.key != "modular" else monthly_total_for_features(selected)
        if amount <= 0:
            self.apply_license(plan_key, selected, payment_status="free")
            return ""
        if self.env.is_development and self.env.dev_auto_approve:
            self.approve_development_purchase(plan_key, selected, amount)
            return ""
        if not self.env.stripe_configured:
            raise AuthError("Stripe checkout backend is not configured. Add TGPA_STRIPE_CHECKOUT_URL in .env.")
        payload = {
            "uid": self.user.uid,
            "name": self.user.name,
            "email": self.user.email,
            "plan": plan_key,
            "features": selected,
            "amount": amount,
            "currency": self.env.currency,
            "success_url": self.env.stripe_success_url,
            "cancel_url": self.env.stripe_cancel_url,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        id_token = str(self._state.get("id_token") or "")
        if id_token:
            headers["Authorization"] = f"Bearer {id_token}"
        request = urllib.request.Request(
            self.env.stripe_checkout_url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=22) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise NetworkUnavailable("Internet connection is required to start Stripe Checkout.") from exc
        checkout_url = str(result.get("url") or result.get("checkout_url") or "")
        if not checkout_url:
            raise AuthError("Stripe checkout backend did not return a checkout URL.")
        payments = self._state.setdefault("payments", [])
        if isinstance(payments, list):
            payments.append(
                {
                    "provider": "stripe",
                    "status": "checkout_started",
                    "plan": plan_key,
                    "features": selected,
                    "amount": amount,
                    "currency": self.env.currency,
                    "session_id": result.get("session_id") or result.get("id") or "",
                    "created_at": utc_now_iso(),
                }
            )
            self.local_store.save(self._state)
        webbrowser.open(checkout_url)
        return checkout_url

    def apply_license(self, plan_key: str, selected_features: Iterable[str], *, payment_status: str) -> None:
        selected = sorted(features_for_plan(plan_key, selected_features))
        amount = 0 if plan_key == "free" else monthly_total_for_features(selected)
        self._state["license"] = {
            "plan": plan_key,
            "status": "active",
            "features": selected,
            "selected_modules": sorted(set(module_for_feature(feature) or "" for feature in selected) - {""}),
            "amount": amount,
            "currency": self.env.currency,
            "payment_status": payment_status,
            "updated_at": utc_now_iso(),
        }
        self.local_store.save(self._state)
        if self.env.firebase_configured and self._state.get("id_token") and self.user is not None:
            try:
                self._write_profile(self._profile_payload(plan=plan_key, features=selected, source=payment_status))
            except AuthError as exc:
                self._last_error = str(exc)

    def approve_development_purchase(self, plan_key: str, selected_features: Iterable[str], amount: int | None = None) -> None:
        selected = sorted(features_for_plan(plan_key, selected_features))
        if amount is None:
            amount = monthly_total_for_features(selected)
        payments = self._state.setdefault("payments", [])
        if isinstance(payments, list):
            payments.append(
                {
                    "provider": "development",
                    "status": "paid",
                    "plan": plan_key,
                    "features": selected,
                    "amount": int(amount),
                    "currency": self.env.currency,
                    "session_id": f"dev_{int(time.time())}",
                    "created_at": utc_now_iso(),
                }
            )
        self.apply_license(plan_key, selected, payment_status="development_paid")

    def sync_from_firebase(self, *, silent: bool = False, create_if_missing: bool = False) -> bool:
        if not self.env.firebase_configured:
            return False
        user = self.user
        id_token = str(self._state.get("id_token") or "")
        if user is None or not id_token:
            return False
        try:
            remote = self.firebase.get_profile(user.uid, id_token)
            if remote is None and create_if_missing:
                remote = self._write_profile(self._profile_payload(plan="free", features=FREE_FEATURES, source="profile-created"))
            if isinstance(remote, dict) and remote:
                self._merge_remote_profile(remote)
                self.local_store.save(self._state)
                return True
        except NetworkUnavailable as exc:
            if not silent:
                raise
            self._last_error = str(exc)
        except AuthError as exc:
            if not silent:
                raise
            self._last_error = str(exc)
        return False

    def _adopt_firebase_auth_result(self, result: dict[str, Any], *, name: str = "") -> None:
        uid = str(result.get("localId") or result.get("user_id") or "")
        email = str(result.get("email") or "")
        display_name = name or str(result.get("displayName") or email.split("@")[0])
        if not uid or not email:
            raise AuthError("Firebase login response did not include a user ID/email.")
        expires_in = int(result.get("expiresIn") or result.get("expires_in") or 3600)
        self._state = {
            "user": {"uid": uid, "name": display_name, "email": email},
            "id_token": result.get("idToken") or result.get("id_token"),
            "refresh_token": result.get("refreshToken") or result.get("refresh_token"),
            "expires_at": time.time() + expires_in - 60,
            "license": {"plan": "free", "status": "active", "features": list(FREE_FEATURES), "updated_at": utc_now_iso()},
            "payments": [],
            "source": "firebase",
        }

    def _write_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        user = self.user
        id_token = str(self._state.get("id_token") or "")
        if user is None or not id_token:
            raise AuthError("Login is required before updating Firebase profile.")
        remote = self.firebase.set_profile(user.uid, id_token, profile)
        self._merge_remote_profile(remote)
        return remote

    def _profile_payload(self, *, plan: str, features: Iterable[str], source: str) -> dict[str, Any]:
        user = self.user
        selected = sorted(set(features) | (set(FREE_FEATURES) if plan == "free" else set()))
        payments = self._state.get("payments", []) if isinstance(self._state, dict) else []
        return {
            "uid": user.uid if user else "",
            "name": user.name if user else "",
            "email": user.email if user else "",
            "product": "TGPAssure Desktop",
            "plan": plan,
            "license_status": "active",
            "features": selected,
            "modules": sorted(set(module_for_feature(feature) or "" for feature in selected) - {""}),
            "module_summary": module_summary(selected),
            "payments": payments if isinstance(payments, list) else [],
            "source": source,
            "updated_at": utc_now_iso(),
        }

    def _merge_remote_profile(self, remote: dict[str, Any]) -> None:
        plan = str(remote.get("plan") or self.current_plan or "free")
        features = remote.get("features") or remote.get("entitlements") or []
        if not isinstance(features, list):
            features = []
        clean_features = sorted({feature for feature in features if feature in FEATURE_BY_KEY})
        if not clean_features:
            clean_features = list(features_for_plan(plan, []))
        if plan == "free":
            clean_features = sorted(set(clean_features) | set(FREE_FEATURES))
        self._state["license"] = {
            "plan": plan,
            "status": str(remote.get("license_status") or "active"),
            "features": clean_features,
            "selected_modules": sorted(set(module_for_feature(feature) or "" for feature in clean_features) - {""}),
            "updated_at": str(remote.get("updated_at") or utc_now_iso()),
            "source": "firebase",
        }
        if isinstance(remote.get("payments"), list):
            self._state["payments"] = remote["payments"]
        if self.user and (remote.get("name") or remote.get("email")):
            self._state["user"] = {
                "uid": self.user.uid,
                "name": str(remote.get("name") or self.user.name),
                "email": str(remote.get("email") or self.user.email),
            }

    def _development_state(
        self,
        *,
        plan: str,
        features: Iterable[str],
        payment_note: str = "development",
        name: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        selected = sorted({feature for feature in features if feature in FEATURE_BY_KEY})
        return {
            "user": {
                "uid": "dev-local-user",
                "name": name or self.env.dev_name,
                "email": email or self.env.dev_email,
            },
            "id_token": "development-token",
            "refresh_token": "development-refresh-token",
            "expires_at": time.time() + 86400 * 365,
            "license": {
                "plan": plan,
                "status": "active",
                "features": selected,
                "selected_modules": sorted(set(module_for_feature(feature) or "" for feature in selected) - {""}),
                "payment_status": payment_note,
                "updated_at": utc_now_iso(),
            },
            "payments": [
                {
                    "provider": "development",
                    "status": "paid",
                    "plan": plan,
                    "features": selected,
                    "amount": 0 if plan == "free" else monthly_total_for_features(selected),
                    "currency": self.env.currency,
                    "session_id": payment_note,
                    "created_at": utc_now_iso(),
                }
            ],
            "source": "development",
        }
