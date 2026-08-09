from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.errors import install_error_handlers
from infrastructure.composition_root import build_management, build_runtime
from infrastructure.readiness import readiness_snapshot

app = FastAPI(title="Nisr", version="0.3.1")
install_error_handlers(app)
UI_DIR = Path(__file__).resolve().parent.parent / "ui"

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")


class RunRequest(BaseModel):
    objective: str
    constraints: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)


@app.get("/", include_in_schema=False)
async def home():
    index = UI_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Nisr UI is not available in this deployment")
    return FileResponse(index)


@app.get("/health")
async def health():
    return {"ok": True, "service": "nisr", "version": "0.3.1"}


@app.get("/readiness")
async def readiness():
    snapshot = await readiness_snapshot()
    return JSONResponse(status_code=200 if snapshot["ok"] else 503, content=snapshot)


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
