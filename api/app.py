from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrastructure.composition_root import build_management, build_runtime

app = FastAPI(title="Nisr", version="0.3.0")


class RunRequest(BaseModel):
    objective: str
    constraints: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)


@app.get("/health")
async def health():
    return {"ok": True, "service": "nisr", "version": "0.3.0"}


@app.post("/run")
async def run_agent(request: RunRequest):
    container = build_runtime(approvals=request.approvals)
    state = await container.orchestrator.run(
        request.objective,
        request.constraints,
        request.approvals,
    )
    return state.model_dump(mode="json")


@app.get("/approvals")
async def approvals(status: str | None = None, limit: int = 100):
    return build_management().approvals.list(status, limit)


@app.post("/approvals/{request_id}/approve")
async def approve(request_id: str):
    try:
        token = build_management().approvals.approve(request_id)
        return {"request_id": request_id, "token": token}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/approvals/{request_id}/deny")
async def deny(request_id: str):
    build_management().approvals.deny(request_id)
    return {"request_id": request_id, "status": "denied"}


@app.get("/audit")
async def audit(limit: int = 100):
    return build_management().audit.tail(limit)


@app.get("/artifacts")
async def artifacts(limit: int = 100):
    return build_management().artifacts.list(limit)

