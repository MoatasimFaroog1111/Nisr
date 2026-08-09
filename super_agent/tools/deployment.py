from __future__ import annotations

import asyncio, shutil
from pathlib import Path
from typing import Any
from super_agent.models import ToolResult, RiskLevel
from super_agent.tools.base import Tool
from super_agent.core.approvals import ApprovalManager


class DeploymentTool(Tool):
    name="deployment"; description="Local/container deployment operations. args: operation(plan|docker_build|docker_run|docker_ps|docker_stop), optional image/tag/name/port/approval_token."
    def __init__(self,workspace:Path,approvals:ApprovalManager):self.workspace=workspace; self.approvals=approvals
    async def _exec(self,args:list[str])->ToolResult:
        if not shutil.which(args[0]):return ToolResult(ok=False,error=f"{args[0]} executable not found")
        proc=await asyncio.create_subprocess_exec(*args,cwd=str(self.workspace),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,err=await proc.communicate();return ToolResult(ok=proc.returncode==0,output=out.decode(errors='replace')[-100000:],error=None if proc.returncode==0 else err.decode(errors='replace')[-50000:],metadata={"returncode":proc.returncode})
    async def run(self,arguments:dict[str,Any])->ToolResult:
        op=str(arguments.get("operation","plan")); token=str(arguments.get("approval_token",""))
        if op=="plan":
            files={p.name for p in self.workspace.iterdir()} if self.workspace.exists() else set(); suggestions=[]
            if "Dockerfile" in files:suggestions.append("Dockerfile detected: docker_build is available")
            if "pyproject.toml" in files:suggestions.append("Python project detected")
            if "package.json" in files:suggestions.append("Node project detected")
            return ToolResult(ok=True,output={"workspace":str(self.workspace),"detected":sorted(files & {"Dockerfile","pyproject.toml","package.json","docker-compose.yml","compose.yml"}),"suggestions":suggestions})
        if op=="docker_ps":return await self._exec(["docker","ps","--format","{{json .}}"])
        image=str(arguments.get("image","super-agent-app")); name=str(arguments.get("name","super-agent-app")); port=str(arguments.get("port","8000"))
        if op=="docker_build":args=["docker","build","-t",image,"."]; payload={"operation":op,"image":image}
        elif op=="docker_run":args=["docker","run","-d","--name",name,"-p",f"{port}:{port}",image]; payload={"operation":op,"image":image,"name":name,"port":port}
        elif op=="docker_stop":args=["docker","stop",name]; payload={"operation":op,"name":name}
        else:return ToolResult(ok=False,error="Unknown deployment operation")
        ok,req=self.approvals.authorize_or_request("deployment",payload,RiskLevel.MEDIUM,token)
        if not ok:return ToolResult(ok=False,error="Deployment operation requires authorization",metadata={"approval_required":req,"risk":"medium"})
        return await self._exec(args)
