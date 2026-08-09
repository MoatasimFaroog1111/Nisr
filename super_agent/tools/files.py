from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
from super_agent.models import ToolResult
from super_agent.tools.base import Tool
from super_agent.core.risk import RiskGate
from super_agent.core.approvals import ApprovalManager


def safe_path(workspace: Path, raw: str) -> Path:
    candidate = (workspace / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    try: candidate.relative_to(workspace.resolve())
    except ValueError: raise ValueError("Path is outside the configured workspace.")
    return candidate


class FileReadTool(Tool):
    name = "read_file"; description = "Read a UTF-8 text file inside workspace. args: path, optional max_chars."
    def __init__(self, workspace: Path): self.workspace = workspace
    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            path=safe_path(self.workspace,str(arguments["path"])); max_chars=int(arguments.get("max_chars",100000))
            data=path.read_text(encoding="utf-8")
            return ToolResult(ok=True,output=data[:max_chars],metadata={"path":str(path)})
        except Exception as e: return ToolResult(ok=False,error=str(e))


class FileListTool(Tool):
    name="list_files"; description="List files/directories inside workspace. args: optional path, optional recursive."
    def __init__(self,workspace:Path): self.workspace=workspace
    async def run(self,arguments:dict[str,Any])->ToolResult:
        try:
            base=safe_path(self.workspace,str(arguments.get("path","."))); recursive=bool(arguments.get("recursive",False))
            items=base.rglob("*") if recursive else base.iterdir(); result=[]
            for p in items:
                result.append({"path":str(p.relative_to(self.workspace)),"type":"dir" if p.is_dir() else "file","size":p.stat().st_size if p.is_file() else None})
                if len(result)>=1000: break
            return ToolResult(ok=True,output=result)
        except Exception as e:return ToolResult(ok=False,error=str(e))


class FileSearchTool(Tool):
    name="search_text"; description="Search UTF-8 text files in workspace for a literal query. args: query, optional path."
    def __init__(self,workspace:Path): self.workspace=workspace
    async def run(self,arguments:dict[str,Any])->ToolResult:
        try:
            query=str(arguments["query"]); base=safe_path(self.workspace,str(arguments.get("path","."))); matches=[]
            for p in base.rglob("*"):
                if not p.is_file() or p.stat().st_size>2_000_000: continue
                try:text=p.read_text(encoding="utf-8")
                except Exception:continue
                for lineno,line in enumerate(text.splitlines(),1):
                    if query.lower() in line.lower():
                        matches.append({"path":str(p.relative_to(self.workspace)),"line":lineno,"text":line[:500]})
                        if len(matches)>=200:return ToolResult(ok=True,output=matches)
            return ToolResult(ok=True,output=matches)
        except Exception as e:return ToolResult(ok=False,error=str(e))


class FileWriteTool(Tool):
    name="write_file"; description="Write UTF-8 text inside workspace. args: path, content, optional approval_token."
    def __init__(self,workspace:Path,risk_gate:RiskGate,approvals:list[str]|None=None,approval_manager:ApprovalManager|None=None):
        self.workspace=workspace; self.risk_gate=risk_gate; self.approvals=approvals or []; self.approval_manager=approval_manager
    async def run(self,arguments:dict[str,Any])->ToolResult:
        try:
            path=safe_path(self.workspace,str(arguments["path"])); content=str(arguments.get("content","")); token=str(arguments.get("approval_token",""))
            risk=self.risk_gate.classify_write(path,self.workspace); payload={"path":str(path),"sha256":hashlib.sha256(content.encode("utf-8")).hexdigest()}
            if self.approval_manager:
                ok,req=self.approval_manager.authorize_or_request("file_write",payload,risk,token,self.approvals)
            else:
                ok=self.risk_gate.is_authorized(risk,self.approvals,token); req=None
            if not ok:return ToolResult(ok=False,error=f"Write requires authorization ({risk.value}).",metadata={"approval_required":req,"risk":risk.value})
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content,encoding="utf-8")
            return ToolResult(ok=True,output=f"Wrote {path}",metadata={"changed_artifact":str(path),"risk":risk.value})
        except Exception as e:return ToolResult(ok=False,error=str(e))
