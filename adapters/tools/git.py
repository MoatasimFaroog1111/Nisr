from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from adapters.tools.base import BaseTool
from domain.contracts import RiskPolicy
from domain.models import ToolResult
from ports.approval import ApprovalPort


class GitTool(BaseTool):
    name = "git"
    description = "Git operations in workspace. args: operation(status|diff|log|branch|add|commit|checkout), optional paths/message/ref/approval_token."

    def __init__(self, workspace: Path, risk: RiskPolicy, approvals: ApprovalPort):
        self._workspace = workspace
        self._risk = risk
        self._approvals = approvals

    async def _run(self, args: list[str]) -> ToolResult:
        if not shutil.which("git"):
            return ToolResult(ok=False, error="git executable not found")
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self._workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return ToolResult(
            ok=process.returncode == 0,
            output=stdout.decode(errors="replace"),
            error=None if process.returncode == 0 else stderr.decode(errors="replace"),
            metadata={"returncode": process.returncode},
        )

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "status"))
        read_only = {
            "status": ["status", "--short", "--branch"],
            "diff": ["diff"],
            "log": ["log", "--oneline", "-n", str(min(int(arguments.get("limit", 20)), 100))],
            "branch": ["branch", "--show-current"],
        }
        if operation in read_only:
            return await self._run(read_only[operation])
        if operation == "add":
            args = ["add", "--"] + [str(x) for x in arguments.get("paths", ["."])]
        elif operation == "commit":
            args = ["commit", "-m", str(arguments.get("message", "Agent update"))]
        elif operation == "checkout":
            args = ["checkout", str(arguments.get("ref", ""))]
        else:
            return ToolResult(ok=False, error="Unknown git operation")
        command = "git " + " ".join(args)
        risk = self._risk.classify_command(command)
        payload = {"operation": operation, "args": args}
        allowed, request = self._approvals.authorize_or_request(
            "git_write",
            payload,
            risk,
            str(arguments.get("approval_token", "")),
        )
        if not allowed:
            return ToolResult(
                ok=False,
                error=f"Git operation requires authorization ({risk.value})",
                metadata={"approval_required": request, "risk": risk.value},
            )
        return await self._run(args)
