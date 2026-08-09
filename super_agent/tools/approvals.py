from __future__ import annotations
from typing import Any
from super_agent.models import ToolResult
from super_agent.tools.base import Tool
from super_agent.core.approvals import ApprovalManager

class ApprovalStatusTool(Tool):
    name="approval_status"; description="Read approval requests. args: optional status, optional limit. Does not approve requests."
    def __init__(self,manager:ApprovalManager):self.manager=manager
    async def run(self,arguments:dict[str,Any])->ToolResult:
        return ToolResult(ok=True,output=self.manager.list(arguments.get("status"),int(arguments.get("limit",50))))
