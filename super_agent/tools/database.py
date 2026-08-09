from __future__ import annotations

import asyncio, sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from super_agent.models import ToolResult
from super_agent.tools.base import Tool
from super_agent.core.risk import RiskGate
from super_agent.core.approvals import ApprovalManager


class DatabaseTool(Tool):
    name="database"; description="Database access using configured AGENT_DATABASE_URL. args: operation(query|execute), sql, optional params, optional approval_token. SQLite built in; PostgreSQL requires database extra."
    def __init__(self,database_url:str,risk:RiskGate,approvals:ApprovalManager):self.url=database_url; self.risk=risk; self.approvals=approvals
    def _sqlite_path(self)->Path:
        if self.url.startswith("sqlite:///"):return Path(self.url[10:]).resolve()
        if self.url.startswith("sqlite://"):return Path(self.url[9:]).resolve()
        raise ValueError("Not a SQLite URL")
    def _sqlite_run(self,sql:str,params:list[Any],query:bool):
        path=self._sqlite_path(); path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as conn:
            cur=conn.execute(sql,params)
            if query:
                cols=[d[0] for d in cur.description or []]; rows=cur.fetchmany(1000); return [dict(zip(cols,row)) for row in rows]
            conn.commit(); return {"rowcount":cur.rowcount}
    def _postgres_run(self,sql:str,params:list[Any],query:bool):
        try:import psycopg
        except ImportError as e:raise RuntimeError('PostgreSQL support requires: pip install -e ".[database]"') from e
        with psycopg.connect(self.url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql,params or None)
                if query:
                    cols=[d.name for d in cur.description or []]; return [dict(zip(cols,row)) for row in cur.fetchmany(1000)]
                conn.commit(); return {"rowcount":cur.rowcount}
    async def run(self,arguments:dict[str,Any])->ToolResult:
        if not self.url:return ToolResult(ok=False,error="AGENT_DATABASE_URL is not configured")
        op=str(arguments.get("operation","query")); sql=str(arguments.get("sql","")).strip(); params=list(arguments.get("params",[])); token=str(arguments.get("approval_token",""))
        if not sql:return ToolResult(ok=False,error="sql is required")
        risk=self.risk.classify_sql(sql)
        if op=="query" and risk.value!="low":return ToolResult(ok=False,error=f"query operation accepts read-only SQL; classified {risk.value}")
        if op=="execute":
            payload={"sql":sql,"params":params}; ok,req=self.approvals.authorize_or_request("database_execute",payload,risk,token)
            if not ok:return ToolResult(ok=False,error=f"Database execute requires authorization ({risk.value})",metadata={"approval_required":req,"risk":risk.value})
        try:
            if self.url.startswith("sqlite:"):out=await asyncio.to_thread(self._sqlite_run,sql,params,op=="query")
            elif self.url.startswith(("postgresql://","postgres://")):out=await asyncio.to_thread(self._postgres_run,sql,params,op=="query")
            else:return ToolResult(ok=False,error="Unsupported database URL scheme")
            return ToolResult(ok=True,output=out,metadata={"risk":risk.value,"operation":op})
        except Exception as e:return ToolResult(ok=False,error=str(e))
