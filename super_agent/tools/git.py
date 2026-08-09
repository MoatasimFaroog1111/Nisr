from __future__ import annotations

import asyncio, shutil
from pathlib import Path
from typing import Any
from super_agent.models import ToolResult
from super_agent.tools.base import Tool
from super_agent.core.risk import RiskGate
from super_agent.core.approvals import ApprovalManager


class GitTool(Tool):
    name="git"; description="Git operations in workspace. args: operation(status|diff|log|branch|add|commit|checkout), optional paths/message/ref/approval_token."
    def __init__(self,workspace:Path,risk:RiskGate,approvals:ApprovalManager):self.workspace=workspace; self.risk=risk; self.approvals=approvals
    async def _run(self,args:list[str])->ToolResult:
        if not shutil.which("git"):return ToolResult(ok=False,error="git executable not found")
        proc=await asyncio.create_subprocess_exec("git",*args,cwd=str(self.workspace),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,err=await proc.communicate(); return ToolResult(ok=proc.returncode==0,output=out.decode(errors="replace"),error=None if proc.returncode==0 else err.decode(errors="replace"),metadata={"returncode":proc.returncode})
    async def run(self,arguments:dict[str,Any])->ToolResult:
        op=str(arguments.get("operation","status")); token=str(arguments.get("approval_token",""))
        mapping={"status":["status","--short","--branch"],"diff":["diff"],"log":["log","--oneline","-n",str(min(int(arguments.get("limit",20)),100))],"branch":["branch","--show-current"]}
        if op in mapping:return await self._run(mapping[op])
        if op=="add": args=["add","--"]+[str(x) for x in arguments.get("paths",["."])]
        elif op=="commit": args=["commit","-m",str(arguments.get("message","Agent update"))]
        elif op=="checkout": args=["checkout",str(arguments.get("ref",""))]
        else:return ToolResult(ok=False,error="Unknown git operation")
        command="git "+" ".join(args); risk=self.risk.classify_command(command); payload={"operation":op,"args":args}
        ok,req=self.approvals.authorize_or_request("git_write",payload,risk,token)
        if not ok:return ToolResult(ok=False,error=f"Git operation requires authorization ({risk.value})",metadata={"approval_required":req,"risk":risk.value})
        return await self._run(args)
