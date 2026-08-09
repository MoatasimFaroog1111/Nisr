from __future__ import annotations

import json
from typing import Any

from domain.models import ToolResult
from ports.audit import AuditPort
from ports.tool import ToolExecutionContext, ToolPort


class ToolRegistry:
    _GENERIC_SECRET_KEYS = {
        "password", "passwd", "secret", "token", "authorization", "api_key", "apikey",
        "approval_token", "otp", "one_time_code", "verification_code", "cvv", "cvc",
        "card_number", "credit_card", "private_key",
    }

    def __init__(self, audit: AuditPort | None = None):
        self._tools: dict[str, ToolPort] = {}
        self._audit = audit

    def register(self, tool: ToolPort) -> None:
        self._tools[tool.name] = tool

    @classmethod
    def _redact(cls, value: Any, extra_keys: set[str] | frozenset[str]) -> Any:
        sensitive = cls._GENERIC_SECRET_KEYS | {str(key).lower() for key in extra_keys}
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).lower()
                output[key] = "[REDACTED]" if normalized in sensitive else cls._redact(item, extra_keys)
            return output
        if isinstance(value, list):
            return [cls._redact(item, extra_keys) for item in value]
        return value

    def sanitize(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        extra = getattr(tool, "sensitive_fields", frozenset()) if tool else frozenset()
        return self._redact(dict(arguments), extra)

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str = "",
        user_id: str = "",
        task_id: str = "",
        actor: str = "agent",
    ) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            result = ToolResult(ok=False, error=f"Unknown tool: {name}")
            if self._audit:
                self._audit.record("tool.unknown", session_id=session_id, data={"name": name})
            return result
        safe_arguments = self.sanitize(name, arguments)
        if self._audit:
            self._audit.record(
                "tool.start",
                session_id=session_id,
                data={"name": name, "arguments": safe_arguments, "actor": actor, "task_id": task_id},
            )
        try:
            contextual = getattr(tool, "run_contextual", None)
            if callable(contextual):
                result = await contextual(
                    arguments,
                    ToolExecutionContext(
                        session_id=session_id,
                        user_id=user_id,
                        task_id=task_id,
                        actor=actor,
                    ),
                )
            else:
                result = await tool.run(arguments)
        except Exception as exc:
            result = ToolResult(ok=False, error=f"Unhandled tool error: {type(exc).__name__}: {exc}")
        if self._audit:
            self._audit.record(
                "tool.finish",
                session_id=session_id,
                data={
                    "name": name,
                    "ok": result.ok,
                    "error": result.error,
                    "metadata": self._redact(result.metadata, frozenset()),
                    "output_preview": str(result.output)[:2000] if result.output is not None else None,
                    "actor": actor,
                    "task_id": task_id,
                },
            )
        return result

    def describe(self) -> str:
        return json.dumps(
            [tool.schema() for tool in self._tools.values()],
            ensure_ascii=False,
            indent=2,
        )

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)
