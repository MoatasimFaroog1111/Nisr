from __future__ import annotations

from typing import Any
import httpx
from super_agent.models import ToolResult, RiskLevel
from super_agent.tools.base import Tool
from super_agent.core.approvals import ApprovalManager


class GitHubTool(Tool):
    name="github"; description="GitHub REST operations. args: operation(repo|get_issues|get_prs|create_issue|comment_issue), owner, repo and relevant fields. Writes require approval."
    def __init__(self,token:str,api_base:str,approvals:ApprovalManager):self.token=token; self.api_base=api_base.rstrip('/'); self.approvals=approvals
    def _headers(self):
        h={"Accept":"application/vnd.github+json","User-Agent":"SuperAgent/0.2"}
        if self.token:h["Authorization"]=f"Bearer {self.token}"
        return h
    async def run(self,arguments:dict[str,Any])->ToolResult:
        op=str(arguments.get("operation","repo")); owner=str(arguments.get("owner","")); repo=str(arguments.get("repo","")); token=str(arguments.get("approval_token",""))
        if not owner or not repo:return ToolResult(ok=False,error="owner and repo are required")
        path=f"/repos/{owner}/{repo}"; method="GET"; body=None
        if op=="repo":pass
        elif op=="get_issues":path+="/issues"
        elif op=="get_prs":path+="/pulls"
        elif op=="create_issue":method="POST"; path+="/issues"; body={"title":str(arguments.get("title","")),"body":str(arguments.get("body",""))}
        elif op=="comment_issue":method="POST"; path+=f"/issues/{int(arguments['number'])}/comments"; body={"body":str(arguments.get("body",""))}
        else:return ToolResult(ok=False,error="Unknown GitHub operation")
        if method!="GET":
            payload={"operation":op,"owner":owner,"repo":repo,"body":body}; ok,req=self.approvals.authorize_or_request("github_write",payload,RiskLevel.MEDIUM,token)
            if not ok:return ToolResult(ok=False,error="GitHub write requires authorization",metadata={"approval_required":req,"risk":"medium"})
            if not self.token:return ToolResult(ok=False,error="AGENT_GITHUB_TOKEN is required for GitHub writes")
        try:
            async with httpx.AsyncClient(timeout=30,headers=self._headers()) as client:r=await client.request(method,self.api_base+path,json=body)
            if r.status_code>=400:return ToolResult(ok=False,error=f"GitHub HTTP {r.status_code}: {r.text[:2000]}")
            return ToolResult(ok=True,output=r.json(),metadata={"status":r.status_code,"operation":op})
        except Exception as e:return ToolResult(ok=False,error=str(e))
