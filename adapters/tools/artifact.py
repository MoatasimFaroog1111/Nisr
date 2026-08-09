from __future__ import annotations

from typing import Any

from adapters.tools.base import BaseTool
from domain.models import ToolResult
from ports.artifact import ArtifactPort


class ArtifactTool(BaseTool):
    name = "artifact"
    description = "Manage generated artifacts. args: operation(write_text|read_text|list), name/content/kind as relevant."

    def __init__(self, artifacts: ArtifactPort):
        self._artifacts = artifacts

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "list"))
        try:
            if operation == "list":
                return ToolResult(ok=True, output=self._artifacts.list(int(arguments.get("limit", 100))))
            if operation == "read_text":
                return ToolResult(
                    ok=True,
                    output=self._artifacts.read_text(
                        str(arguments["name"]), int(arguments.get("max_chars", 100_000))
                    ),
                )
            if operation == "write_text":
                record = self._artifacts.write_text(
                    str(arguments.get("name", "artifact.txt")),
                    str(arguments.get("content", "")),
                    kind=str(arguments.get("kind", "text")),
                )
                return ToolResult(
                    ok=True,
                    output=record,
                    metadata={"changed_artifact": record["path"]},
                )
            return ToolResult(ok=False, error="Unknown artifact operation")
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
