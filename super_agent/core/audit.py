from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SECRET_KEYS = {"api_key", "token", "authorization", "password", "secret", "approval_token"}


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in _SECRET_KEYS or any(part in key.lower() for part in ("secret", "password", "token", "api_key")):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    text = str(value) if value is not None else value
    if isinstance(text, str) and len(text) > 20000:
        return text[:20000] + "...[truncated]"
    return value


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, event: str, *, session_id: str = "", actor: str = "agent", data: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "session_id": session_id,
            "actor": actor,
            "data": _redact(data or {}),
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
