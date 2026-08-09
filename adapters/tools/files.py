from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from adapters.tools.base import BaseTool
from domain.contracts import RiskPolicy
from domain.models import ToolResult
from ports.approval import ApprovalPort


def safe_path(workspace: Path, raw: str) -> Path:
    candidate = (workspace / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError("Path is outside the configured workspace") from exc
    return candidate


class FileReadTool(BaseTool):
    name = "read_file"
    description = "Read a UTF-8 text file inside workspace. args: path, optional max_chars."

    def __init__(self, workspace: Path):
        self._workspace = workspace

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            path = safe_path(self._workspace, str(arguments["path"]))
            data = path.read_text(encoding="utf-8")
            return ToolResult(
                ok=True,
                output=data[: int(arguments.get("max_chars", 100_000))],
                metadata={"path": str(path)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))


class FileListTool(BaseTool):
    name = "list_files"
    description = "List files/directories inside workspace. args: optional path, optional recursive."

    def __init__(self, workspace: Path):
        self._workspace = workspace

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            base = safe_path(self._workspace, str(arguments.get("path", ".")))
            items = base.rglob("*") if bool(arguments.get("recursive", False)) else base.iterdir()
            output = []
            for path in items:
                output.append(
                    {
                        "path": str(path.relative_to(self._workspace)),
                        "type": "dir" if path.is_dir() else "file",
                        "size": path.stat().st_size if path.is_file() else None,
                    }
                )
                if len(output) >= 1000:
                    break
            return ToolResult(ok=True, output=output)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))


class FileSearchTool(BaseTool):
    name = "search_text"
    description = "Search UTF-8 text files in workspace for a literal query. args: query, optional path."

    def __init__(self, workspace: Path):
        self._workspace = workspace

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            query = str(arguments["query"])
            base = safe_path(self._workspace, str(arguments.get("path", ".")))
            matches = []
            for path in base.rglob("*"):
                if not path.is_file() or path.stat().st_size > 2_000_000:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    continue
                for line_number, line in enumerate(text.splitlines(), 1):
                    if query.lower() in line.lower():
                        matches.append(
                            {
                                "path": str(path.relative_to(self._workspace)),
                                "line": line_number,
                                "text": line[:500],
                            }
                        )
                        if len(matches) >= 200:
                            return ToolResult(ok=True, output=matches)
            return ToolResult(ok=True, output=matches)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))


class FileWriteTool(BaseTool):
    name = "write_file"
    description = "Write UTF-8 text inside workspace. args: path, content, optional approval_token."

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
        try:
            path = safe_path(self._workspace, str(arguments["path"]))
            content = str(arguments.get("content", ""))
            risk = self._risk.classify_write(path, self._workspace)
            payload = {
                "path": str(path),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            allowed, request = self._approvals.authorize_or_request(
                "file_write",
                payload,
                risk,
                str(arguments.get("approval_token", "")),
                self._legacy_approvals,
            )
            if not allowed:
                return ToolResult(
                    ok=False,
                    error=f"Write requires authorization ({risk.value})",
                    metadata={"approval_required": request, "risk": risk.value},
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                ok=True,
                output=f"Wrote {path}",
                metadata={"changed_artifact": str(path), "risk": risk.value},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
