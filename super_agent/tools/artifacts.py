from __future__ import annotations

from typing import Any
from super_agent.models import ToolResult
from super_agent.tools.base import Tool
from super_agent.core.artifacts import ArtifactManager


class ArtifactTool(Tool):
    name="artifact"; description="Manage generated artifacts. args: operation(write_text|read_text|list), name/content/kind as relevant."
    def __init__(self,manager:ArtifactManager):self.manager=manager
    async def run(self,arguments:dict[str,Any])->ToolResult:
        op=str(arguments.get("operation","list"))
        try:
            if op=="list":return ToolResult(ok=True,output=self.manager.list(int(arguments.get("limit",100))))
            if op=="read_text":return ToolResult(ok=True,output=self.manager.read_text(str(arguments["name"]),int(arguments.get("max_chars",100000))))
            if op=="write_text":
                rec=self.manager.write_text(str(arguments.get("name","artifact.txt")),str(arguments.get("content","")),kind=str(arguments.get("kind","text")))
                return ToolResult(ok=True,output=rec,metadata={"changed_artifact":rec["path"]})
            return ToolResult(ok=False,error="Unknown artifact operation")
        except Exception as e:return ToolResult(ok=False,error=str(e))
