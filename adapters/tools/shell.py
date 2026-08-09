from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from adapters.tools.base import BaseTool
from domain.contracts import RiskPolicy
from domain.models import RiskLevel, ToolResult
from ports.approval import ApprovalPort


class ShellTool(BaseTool):
    name = "shell"
    description = "Run a non-interactive shell command in workspace. args: command, optional approval_token, optional timeout."

    def __init__(
        self,
        workspace: Path,
        risk: RiskPolicy,
        approvals: ApprovalPort,
        legacy_approvals: list[str] | None = None,
    ):
        self._workspace = workspace
        self._risk = risk
        self._approvals = approvals
        self._legacy_approvals = legacy_approvals or []

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = str(arguments.get("command", "")).strip()
        if not command:
            return ToolResult(ok=False, error="command is required")
        risk = self._risk.classify_command(command)
        if bool(arguments.get("verification_only", False)) and risk != RiskLevel.LOW:
            return ToolResult(ok=False, error=f"Verification command is not low-risk ({risk.value})")
        payload = {"command": command, "cwd": str(self._workspace)}
        allowed, request = self._approvals.authorize_or_request(
            "shell",
            payload,
            risk,
            str(arguments.get("approval_token", "")),
            self._legacy_approvals,
        )
        if not allowed:
            return ToolResult(
                ok=False,
                error=f"Command requires authorization ({risk.value})",
                metadata={"approval_required": request, "risk": risk.value},
            )
        timeout = float(arguments.get("timeout", 60))
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self._workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")
            error = stderr.decode(errors="replace")
            return ToolResult(
                ok=process.returncode == 0,
                output=output[-100_000:],
                error=None if process.returncode == 0 else error[-50_000:],
                metadata={"returncode": process.returncode, "risk": risk.value},
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return ToolResult(ok=False, error=f"Command timed out after {timeout}s")
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
