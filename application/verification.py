from __future__ import annotations

from domain.models import VerificationResult
from ports.tool import ToolRegistryPort


class VerificationService:
    def __init__(self, tools: ToolRegistryPort):
        self._tools = tools

    async def verify(self, commands: list[str], session_id: str = "") -> VerificationResult:
        if not commands:
            return VerificationResult(
                ok=True, checks=[], summary="No explicit verification commands."
            )
        checks: list[dict] = []
        overall = True
        for command in commands:
            result = await self._tools.call(
                "shell",
                {"command": command, "verification_only": True},
                session_id=session_id,
            )
            checks.append(
                {
                    "command": command,
                    "ok": result.ok,
                    "output": result.output,
                    "error": result.error,
                }
            )
            overall = overall and result.ok
        return VerificationResult(
            ok=overall,
            checks=checks,
            summary="Verification passed." if overall else "Verification failed.",
        )
