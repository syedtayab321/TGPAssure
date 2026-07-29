from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.auth.env import AuthEnvironment


class AuthError(RuntimeError):
    pass


class NetworkUnavailable(AuthError):
    pass


class FirebaseClient:
    def __init__(self, env: AuthEnvironment, timeout: float = 18.0) -> None:
        self.env = env
        self.timeout = timeout

    def _json_request(
        self,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        method: str = "POST",
        bearer: str | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            message = self._extract_error_message(raw) or f"HTTP {exc.code}"
            raise AuthError(message) from exc
        except urllib.error.URLError as exc:
            raise NetworkUnavailable("Internet connection is required for Firebase login, account creation and cloud payment sync.") from exc
        except TimeoutError as exc:
            raise NetworkUnavailable("Firebase request timed out. Check the internet connection and try again.") from exc

    @staticmethod
    def _extract_error_message(raw: str) -> str:
        try:
            parsed = json.loads(raw)
            message = parsed.get("error", {}).get("message")
            if isinstance(message, str):
                friendly = {
                    "EMAIL_EXISTS": "This email is already registered. Use Login instead.",
                    "EMAIL_NOT_FOUND": "No account exists for this email. Create an account first.",
                    "INVALID_PASSWORD": "Incorrect password.",
                    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
                    "USER_DISABLED": "This account is disabled.",
                    "WEAK_PASSWORD : Password should be at least 6 characters": "Password should be at least 6 characters.",
                }.get(message)
                return friendly or message.replace("_", " ").title()
        except Exception:
            pass
        return raw[:300]

    def _identity_url(self, endpoint: str) -> str:
        if not self.env.firebase_api_key:
            raise AuthError("Firebase API key is missing. Add FIREBASE_API_KEY in .env.")
        return f"https://identitytoolkit.googleapis.com/v1/{endpoint}?key={urllib.parse.quote(self.env.firebase_api_key)}"

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        return self._json_request(
            self._identity_url("accounts:signInWithPassword"),
            {"email": email, "password": password, "returnSecureToken": True},
        )

    def create_user(self, name: str, email: str, password: str) -> dict[str, Any]:
        result = self._json_request(
            self._identity_url("accounts:signUp"),
            {"email": email, "password": password, "returnSecureToken": True},
        )
        id_token = result.get("idToken")
        if id_token and name:
            try:
                self._json_request(
                    self._identity_url("accounts:update"),
                    {"idToken": id_token, "displayName": name, "returnSecureToken": True},
                )
            except AuthError:
                pass
        return result

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        if not self.env.firebase_api_key:
            raise AuthError("Firebase API key is missing. Add FIREBASE_API_KEY in .env.")
        url = f"https://securetoken.googleapis.com/v1/token?key={urllib.parse.quote(self.env.firebase_api_key)}"
        data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise AuthError(self._extract_error_message(raw) or f"HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise NetworkUnavailable("Internet connection is required to refresh the Firebase login session.") from exc

    def lookup_user(self, id_token: str) -> dict[str, Any]:
        return self._json_request(self._identity_url("accounts:lookup"), {"idToken": id_token})

    def _document_url(self, uid: str) -> str:
        if not self.env.firebase_project_id:
            raise AuthError("Firebase project ID is missing. Add FIREBASE_PROJECT_ID in .env.")
        quoted_db = urllib.parse.quote(self.env.firestore_database, safe="")
        quoted_uid = urllib.parse.quote(uid, safe="")
        return (
            f"https://firestore.googleapis.com/v1/projects/"
            f"{urllib.parse.quote(self.env.firebase_project_id)}/databases/{quoted_db}/documents/"
            f"tgpassure_users/{quoted_uid}"
        )

    def get_profile(self, uid: str, id_token: str) -> dict[str, Any] | None:
        try:
            doc = self._json_request(self._document_url(uid), None, method="GET", bearer=id_token)
            return self._decode_document(doc)
        except AuthError as exc:
            if "404" in str(exc) or "not found" in str(exc).lower():
                return None
            raise

    def set_profile(self, uid: str, id_token: str, profile: dict[str, Any]) -> dict[str, Any]:
        fields = {key: self._encode_value(value) for key, value in profile.items()}
        doc = {"fields": fields}
        response = self._json_request(self._document_url(uid), doc, method="PATCH", bearer=id_token)
        return self._decode_document(response)

    @classmethod
    def _encode_value(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {"nullValue": None}
        if isinstance(value, bool):
            return {"booleanValue": value}
        if isinstance(value, int) and not isinstance(value, bool):
            return {"integerValue": str(value)}
        if isinstance(value, float):
            return {"doubleValue": value}
        if isinstance(value, str):
            return {"stringValue": value}
        if isinstance(value, (list, tuple, set)):
            return {"arrayValue": {"values": [cls._encode_value(item) for item in value]}}
        if isinstance(value, dict):
            return {"mapValue": {"fields": {str(k): cls._encode_value(v) for k, v in value.items()}}}
        return {"stringValue": str(value)}

    @classmethod
    def _decode_value(cls, value: dict[str, Any]) -> Any:
        if "nullValue" in value:
            return None
        if "booleanValue" in value:
            return bool(value["booleanValue"])
        if "integerValue" in value:
            try:
                return int(value["integerValue"])
            except Exception:
                return value["integerValue"]
        if "doubleValue" in value:
            return float(value["doubleValue"])
        if "stringValue" in value:
            return value["stringValue"]
        if "timestampValue" in value:
            return value["timestampValue"]
        if "arrayValue" in value:
            return [cls._decode_value(item) for item in value.get("arrayValue", {}).get("values", [])]
        if "mapValue" in value:
            return {key: cls._decode_value(val) for key, val in value.get("mapValue", {}).get("fields", {}).items()}
        return None

    @classmethod
    def _decode_document(cls, doc: dict[str, Any]) -> dict[str, Any]:
        fields = doc.get("fields", {}) if isinstance(doc, dict) else {}
        return {key: cls._decode_value(value) for key, value in fields.items()}
