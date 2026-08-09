from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SENSITIVE = {"password", "secret", "token", "authorization", "api_key", "approval_token"}


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE or any(x in key.lower() for x in ("secret", "token", "password", "api_key")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str) and len(value) > 20_000:
        return value[:20_000] + "...[truncated]"
    return value


class JsonlAuditAdapter:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(
        self,
        event: str,
        *,
        session_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "session_id": session_id,
            "data": _redact(data or {}),
        }
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        output: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                output.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return output
