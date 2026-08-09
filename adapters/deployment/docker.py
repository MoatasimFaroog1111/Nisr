from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from adapters.tools.base import BaseTool
from domain.models import RiskLevel, ToolResult
from ports.approval import ApprovalPort


class DockerDeploymentTool(BaseTool):
    name = "deployment"
    description = "Container deployment operations. args: operation(plan|docker_build|docker_run|docker_ps|docker_stop), optional image/name/port/approval_token."

    def __init__(self, workspace: Path, approvals: ApprovalPort):
        self._workspace = workspace
        self._approvals = approvals

    async def _exec(self, args: list[str]) -> ToolResult:
        if not shutil.which(args[0]):
            return ToolResult(ok=False, error=f"{args[0]} executable not found")
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self._workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return ToolResult(
            ok=process.returncode == 0,
            output=stdout.decode(errors="replace")[-100_000:],
            error=None if process.returncode == 0 else stderr.decode(errors="replace")[-50_000:],
            metadata={"returncode": process.returncode},
        )

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "plan"))
        if operation == "plan":
            files = {path.name for path in self._workspace.iterdir()} if self._workspace.exists() else set()
            return ToolResult(
                ok=True,
                output={
                    "workspace": str(self._workspace),
                    "detected": sorted(files & {"Dockerfile", "pyproject.toml", "package.json", "docker-compose.yml", "compose.yml"}),
                },
            )
        if operation == "docker_ps":
            return await self._exec(["docker", "ps", "--format", "{{json .}}"])
        image = str(arguments.get("image", "nisr-app"))
        name = str(arguments.get("name", "nisr-app"))
        port = str(arguments.get("port", "8000"))
        if operation == "docker_build":
            args = ["docker", "build", "-t", image, "."]
            payload = {"operation": operation, "image": image}
        elif operation == "docker_run":
            args = ["docker", "run", "-d", "--name", name, "-p", f"{port}:{port}", image]
            payload = {"operation": operation, "image": image, "name": name, "port": port}
        elif operation == "docker_stop":
            args = ["docker", "stop", name]
            payload = {"operation": operation, "name": name}
        else:
            return ToolResult(ok=False, error="Unknown deployment operation")
        allowed, request = self._approvals.authorize_or_request(
            "deployment",
            payload,
            RiskLevel.MEDIUM,
            str(arguments.get("approval_token", "")),
        )
        if not allowed:
            return ToolResult(
                ok=False,
                error="Deployment operation requires authorization",
                metadata={"approval_required": request, "risk": "medium"},
            )
        return await self._exec(args)
