from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from super_agent.models import ToolResult, RiskLevel
from super_agent.tools.base import Tool
from super_agent.core.risk import RiskGate
from super_agent.core.approvals import ApprovalManager


class ShellTool(Tool):
    name="shell"; description="Run a non-interactive shell command in workspace. args: command, optional approval_token, optional timeout."
    def __init__(self,workspace:Path,risk_gate:RiskGate,approvals:list[str]|None=None,approval_manager:ApprovalManager|None=None):
        self.workspace=workspace; self.risk_gate=risk_gate; self.approvals=approvals or []; self.approval_manager=approval_manager
    async def run(self,arguments:dict[str,Any])->ToolResult:
        command=str(arguments.get("command","")).strip()
        if not command:return ToolResult(ok=False,error="command is required")
        risk=self.risk_gate.classify_command(command); verification_only=bool(arguments.get("verification_only",False))
        if verification_only and risk!=RiskLevel.LOW:return ToolResult(ok=False,error=f"Verification command is not low-risk ({risk.value}).")
        token=str(arguments.get("approval_token","")); payload={"command":command,"cwd":str(self.workspace)}
        if self.approval_manager: ok,req=self.approval_manager.authorize_or_request("shell",payload,risk,token,self.approvals)
        else: ok=self.risk_gate.is_authorized(risk,self.approvals,token); req=None
        if not ok:return ToolResult(ok=False,error=f"Command requires authorization ({risk.value}).",metadata={"approval_required":req,"risk":risk.value})
        timeout=float(arguments.get("timeout",60))
        try:
            proc=await asyncio.create_subprocess_shell(command,cwd=str(self.workspace),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr=await asyncio.wait_for(proc.communicate(),timeout=timeout); out=stdout.decode(errors="replace"); err=stderr.decode(errors="replace")
            return ToolResult(ok=proc.returncode==0,output=out[-100000:],error=None if proc.returncode==0 else err[-50000:],metadata={"returncode":proc.returncode,"risk":risk.value})
        except asyncio.TimeoutError:
            try:proc.kill()
            except Exception:pass
            return ToolResult(ok=False,error=f"Command timed out after {timeout}s.")
        except Exception as e:return ToolResult(ok=False,error=str(e))
