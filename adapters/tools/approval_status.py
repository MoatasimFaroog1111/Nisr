from __future__ import annotations

from typing import Any

from adapters.tools.base import BaseTool
from domain.models import ToolResult
from ports.approval import ApprovalPort


class ApprovalStatusTool(BaseTool):
    name = "approval_status"
    description = "Read approval requests. args: optional status, optional limit. Does not approve requests."

    def __init__(self, approvals: ApprovalPort):
        self._approvals = approvals

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            ok=True,
            output=self._approvals.list(
                arguments.get("status"), int(arguments.get("limit", 50))
            ),
        )
