from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.browser import USER_COOKIE, router as browser_router, verify_run_browser_access
from api.errors import install_error_handlers
from api.serialization import public_agent_state
from infrastructure.composition_root import build_browser_runtime, build_management, build_runtime
from infrastructure.readiness import readiness_snapshot
from infrastructure.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    browser_runtime = build_browser_runtime(settings)
    app.state.browser_runtime = browser_runtime

    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(max(10, settings.browser_cleanup_interval_seconds))
            try:
                await browser_runtime.service.cleanup_expired()
            except Exception:
                # Viewer/session cleanup must never crash the API process.
                pass

    cleanup_task = asyncio.create_task(cleanup_loop(), name="browser-session-cleanup")
    try:
        yield
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
        await browser_runtime.close()


app = FastAPI(title="Nisr", version="0.4.0", lifespan=lifespan)
install_error_handlers(app)
app.include_router(browser_router)
UI_DIR = Path(__file__).resolve().parent.parent / "ui"

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")


class RunRequest(BaseModel):
    objective: str
    constraints: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    session_id: str | None = None


@app.get("/", include_in_schema=False)
async def home():
    index = UI_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Nisr UI is not available in this deployment")
    return FileResponse(index)


@app.get("/health")
async def health():
    return {"ok": True, "service": "nisr", "version": "0.4.0"}


@app.get("/readiness")
async def readiness(request: Request):
    snapshot = await readiness_snapshot(settings, request.app.state.browser_runtime.provider)
    snapshot["version"] = "0.4.0"
    return JSONResponse(status_code=200 if snapshot["ok"] else 503, content=snapshot)


@app.post("/run")
async def run_agent(payload: RunRequest, request: Request):
    browser_runtime = request.app.state.browser_runtime
    user_id = "api"
    session_id = payload.session_id
    if session_id:
        token = request.headers.get("x-nisr-browser-token", "")
        browser_runtime, user_id = verify_run_browser_access(request, session_id, token)
        await browser_runtime.service.register_session(session_id, user_id)

    container = build_runtime(
        approvals=payload.approvals,
        browser_runtime=browser_runtime,
    )
    state = await container.orchestrator.run(
        payload.objective,
        payload.constraints,
        payload.approvals,
        session_id=session_id,
        user_id=user_id,
        browser_session_id=session_id,
    )
    return public_agent_state(state)


def _request_user_id(request: Request) -> str | None:
    return request.cookies.get(USER_COOKIE)


def _assert_session_owner(container, request_id: str, user_id: str | None) -> str | None:
    session_id = container.sessions.find_session_by_approval(request_id)
    if not session_id:
        return None
    state = container.sessions.load(session_id)
    if user_id and state and state.user_id != user_id:
        raise HTTPException(status_code=403, detail="Approval belongs to a different user session")
    return session_id


@app.get("/approvals")
async def approvals(request: Request, status: str | None = None, limit: int = 100):
    browser_runtime = request.app.state.browser_runtime
    container = build_runtime(browser_runtime=browser_runtime)
    rows = container.approvals.list(status, limit)
    user_id = _request_user_id(request)
    if not user_id:
        return rows
    visible = []
    for row in rows:
        session_id = container.sessions.find_session_by_approval(row["request_id"])
        if not session_id:
            continue
        state = container.sessions.load(session_id)
        if state and state.user_id == user_id:
            visible.append(row)
    return visible


@app.post("/approvals/{request_id}/approve")
async def approve(request_id: str, request: Request):
    browser_runtime = request.app.state.browser_runtime
    management = build_management()
    container = build_runtime(browser_runtime=browser_runtime)
    session_id = _assert_session_owner(container, request_id, _request_user_id(request))
    try:
        token = management.approvals.approve(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not session_id:
        return {
            "request_id": request_id,
            "status": "approved",
            "resumed": False,
            "message": "Approval granted. No resumable session was linked to this older request.",
        }

    resumed_container = build_runtime(approvals=[token], browser_runtime=browser_runtime)
    try:
        state = await resumed_container.orchestrator.resume(
            session_id,
            approvals=[token],
            approved_request_id=request_id,
        )
        return {
            "request_id": request_id,
            "status": "approved",
            "resumed": True,
            "session_id": session_id,
            "state": public_agent_state(state),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/approvals/{request_id}/deny")
async def deny(request_id: str, request: Request):
    browser_runtime = request.app.state.browser_runtime
    container = build_runtime(browser_runtime=browser_runtime)
    session_id = _assert_session_owner(container, request_id, _request_user_id(request))
    container.approvals.deny(request_id)
    if not session_id:
        return {
            "request_id": request_id,
            "status": "denied",
            "resumed": False,
        }
    state = container.orchestrator.deny(session_id, request_id)
    return {
        "request_id": request_id,
        "status": "denied",
        "resumed": False,
        "session_id": session_id,
        "state": public_agent_state(state),
    }


@app.get("/audit")
async def audit(limit: int = 100):
    return build_management().audit.tail(limit)


@app.get("/artifacts")
async def artifacts(limit: int = 100):
    return build_management().artifacts.list(limit)
