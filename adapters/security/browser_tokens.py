from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class BrowserSessionTokenService:
    """Creates short-lived browser-session tokens for HTTP/WebSocket ownership checks."""

    def __init__(self, secret: str, ttl_seconds: int = 3600):
        if not secret:
            raise ValueError("Browser session secret is required")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = max(60, int(ttl_seconds))

    @staticmethod
    def _b64encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))

    def issue(self, *, session_id: str, user_id: str) -> str:
        payload = {
            "sid": session_id,
            "uid": user_id,
            "exp": int(time.time()) + self._ttl_seconds,
        }
        encoded = self._b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"bs1.{encoded}.{self._b64encode(signature)}"

    def verify(self, token: str, *, session_id: str | None = None, user_id: str | None = None) -> dict[str, Any] | None:
        try:
            prefix, encoded, signature = token.split(".", 2)
            if prefix != "bs1":
                return None
            expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            supplied = self._b64decode(signature)
            if not hmac.compare_digest(expected, supplied):
                return None
            payload = json.loads(self._b64decode(encoded).decode("utf-8"))
            if int(payload.get("exp", 0)) <= int(time.time()):
                return None
            if session_id is not None and payload.get("sid") != session_id:
                return None
            if user_id is not None and payload.get("uid") != user_id:
                return None
            return payload
        except Exception:
            return None
