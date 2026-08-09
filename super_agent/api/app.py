from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from super_agent.runtime import build_runtime
from super_agent.config import settings
from super_agent.core.approvals import ApprovalManager
from super_agent.core.audit import AuditLog
from super_agent.core.artifacts import ArtifactManager

app=FastAPI(title="Super Agent Production",version="0.2.0")

class RunRequest(BaseModel):
    objective:str; constraints:list[str]=Field(default_factory=list); approvals:list[str]=Field(default_factory=list)

@app.get("/health")
async def health():return {"ok":True,"service":"super-agent-production","version":"0.2.0"}

@app.post("/run")
async def run_agent(request:RunRequest):
    runtime=build_runtime(approvals=request.approvals); state=await runtime.run(request.objective,request.constraints,request.approvals); return state.model_dump(mode="json")

@app.get("/approvals")
async def approvals(status:str|None=None,limit:int=100):
    return ApprovalManager(settings.approval_db,settings.approval_secret,settings.auto_approve_low_risk).list(status,limit)

@app.post("/approvals/{request_id}/approve")
async def approve(request_id:str):
    try:token=ApprovalManager(settings.approval_db,settings.approval_secret,settings.auto_approve_low_risk).approve(request_id);return {"request_id":request_id,"token":token}
    except (KeyError,ValueError) as e:raise HTTPException(status_code=404 if isinstance(e,KeyError) else 400,detail=str(e))

@app.post("/approvals/{request_id}/deny")
async def deny(request_id:str):
    ApprovalManager(settings.approval_db,settings.approval_secret,settings.auto_approve_low_risk).deny(request_id);return {"request_id":request_id,"status":"denied"}

@app.get("/audit")
async def audit(limit:int=100):return AuditLog(settings.audit_log).tail(limit)

@app.get("/artifacts")
async def artifacts(limit:int=100):return ArtifactManager(settings.artifacts_dir).list(limit)
