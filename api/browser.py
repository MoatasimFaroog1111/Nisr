from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from api.serialization import public_agent_state
from domain.browser import BrowserEvent
from infrastructure.composition_root import BrowserRuntimeContainer, build_runtime


router = APIRouter()
USER_COOKIE = "nisr_browser_user"
TOKEN_HEADER = "x-nisr-browser-token"
WS_PROTOCOL = "nisr-browser"


def _browser_runtime(scope) -> BrowserRuntimeContainer:
    runtime = getattr(scope.app.state, "browser_runtime", None)
    if runtime is None:
        raise RuntimeError("Browser runtime is not initialized")
    return runtime


def _user_id_from_request(request: Request) -> str | None:
    return request.cookies.get(USER_COOKIE)


def _verify_http_access(request: Request, session_id: str) -> tuple[BrowserRuntimeContainer, str]:
    runtime = _browser_runtime(request)
    user_id = _user_id_from_request(request)
    token = request.headers.get(TOKEN_HEADER, "")
    if not user_id or not token:
        raise HTTPException(status_code=401, detail="Browser session authentication is required")
    payload = runtime.tokens.verify(token, session_id=session_id, user_id=user_id)
    if not payload:
        raise HTTPException(status_code=403, detail="Invalid or expired browser session token")
    return runtime, user_id


def verify_run_browser_access(request: Request, session_id: str, token: str) -> tuple[BrowserRuntimeContainer, str]:
    runtime = _browser_runtime(request)
    user_id = _user_id_from_request(request)
    if not user_id or not token:
        raise HTTPException(status_code=401, detail="Browser session authentication is required")
    payload = runtime.tokens.verify(token, session_id=session_id, user_id=user_id)
    if not payload:
        raise HTTPException(status_code=403, detail="Invalid or expired browser session token")
    return runtime, user_id


@router.post("/browser/sessions")
async def create_browser_session(request: Request):
    runtime = _browser_runtime(request)
    user_id = _user_id_from_request(request) or uuid4().hex
    session_id = uuid4().hex
    await runtime.service.register_session(session_id, user_id)
    token = runtime.tokens.issue(session_id=session_id, user_id=user_id)
    response = JSONResponse(
        {
            "session_id": session_id,
            "token": token,
            "websocket_path": f"/ws/browser/{session_id}",
            "owner": "agent",
            "control_state": "AGENT_CONTROL",
        }
    )
    response.set_cookie(
        USER_COOKIE,
        user_id,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return response


@router.get("/browser/sessions/{session_id}")
async def browser_state(session_id: str, request: Request):
    runtime, user_id = _verify_http_access(request, session_id)
    state = await runtime.service.get_state(session_id, user_id)
    return state.model_dump(mode="json")


@router.post("/browser/sessions/{session_id}/take-control")
async def take_control(session_id: str, request: Request):
    runtime, user_id = _verify_http_access(request, session_id)
    state = await runtime.service.take_control(session_id, user_id)
    return {"ok": True, "state": state.model_dump(mode="json")}


@router.post("/browser/sessions/{session_id}/return-control")
async def return_control(session_id: str, request: Request):
    runtime, user_id = _verify_http_access(request, session_id)
    browser_state = await runtime.service.return_control(session_id, user_id)
    container = build_runtime(browser_runtime=runtime)
    stored = container.sessions.load(session_id)
    if stored and stored.user_id != user_id:
        raise HTTPException(status_code=403, detail="Agent session belongs to a different user")
    resumed = await container.orchestrator.resume_user(
        session_id,
        {
            "url": browser_state.url,
            "title": browser_state.title,
            "tabs": [tab.model_dump(mode="json") for tab in browser_state.tabs],
            "sensitive_signals": browser_state.sensitive_signals,
            "control_state": browser_state.control_state.value,
            "reliability": browser_state.reliability,
        },
    ) if stored else None
    return {
        "ok": True,
        "browser": browser_state.model_dump(mode="json"),
        "resumed": resumed is not None,
        "state": public_agent_state(resumed) if resumed else None,
    }


@router.delete("/browser/sessions/{session_id}")
async def close_browser_session(session_id: str, request: Request):
    runtime, user_id = _verify_http_access(request, session_id)
    await runtime.service.close_session(session_id, user_id)
    return {"ok": True, "session_id": session_id}


def _ws_token(websocket: WebSocket) -> str:
    raw = websocket.headers.get("sec-websocket-protocol", "")
    protocols = [item.strip() for item in raw.split(",") if item.strip()]
    if not protocols or protocols[0] != WS_PROTOCOL or len(protocols) < 2:
        return ""
    return protocols[1]


async def _browser_ws_sender(websocket: WebSocket, subscription) -> None:
    while True:
        event = await subscription.receive()
        await websocket.send_json(event.model_dump(mode="json"))


async def _browser_ws_receiver(
    websocket: WebSocket,
    runtime: BrowserRuntimeContainer,
    session_id: str,
    user_id: str,
) -> None:
    while True:
        message = await websocket.receive_json()
        message_type = str(message.get("type", ""))
        if message_type == "browser.ping":
            await runtime.events.publish(BrowserEvent(type="browser.pong", session_id=session_id, actor="system"))
            continue
        if message_type != "browser.user_input":
            await runtime.events.publish(
                BrowserEvent(
                    type="browser.error", session_id=session_id, actor="user",
                    message="Unsupported realtime browser message", data={"code": "UNSUPPORTED_MESSAGE"},
                )
            )
            continue
        action = str(message.get("action", ""))
        payload = dict(message.get("payload") or {})
        try:
            await runtime.service.user_action(session_id, user_id, action, payload)
        except Exception as exc:
            await runtime.events.publish(
                BrowserEvent(
                    type="browser.error", session_id=session_id, actor="user",
                    message="Browser input could not be applied", data={"code": type(exc).__name__},
                )
            )


@router.websocket("/ws/browser/{session_id}")
async def browser_websocket(websocket: WebSocket, session_id: str):
    runtime = _browser_runtime(websocket)
    user_id = websocket.cookies.get(USER_COOKIE)
    token = _ws_token(websocket)
    if not user_id or not token or not runtime.tokens.verify(token, session_id=session_id, user_id=user_id):
        await websocket.close(code=4401)
        return

    try:
        await runtime.service.register_session(session_id, user_id)
        current = await runtime.service.get_state(session_id, user_id)
    except Exception:
        await websocket.close(code=4403)
        return

    await websocket.accept(subprotocol=WS_PROTOCOL)
    subscription = await runtime.events.subscribe(session_id)
    await runtime.streamer.acquire(session_id, user_id)
    await runtime.events.publish(
        BrowserEvent(
            type="browser.session_ready",
            session_id=session_id,
            actor="system",
            message="Live browser channel connected",
            data={
                "owner": current.owner.value,
                "control_state": current.control_state.value,
                "url": current.url,
                "title": current.title,
                "tabs": [tab.model_dump(mode="json") for tab in current.tabs],
                "reliability": current.reliability,
            },
        )
    )

    sender = asyncio.create_task(_browser_ws_sender(websocket, subscription))
    receiver = asyncio.create_task(_browser_ws_receiver(websocket, runtime, session_id, user_id))
    try:
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if not task.cancelled():
                task.exception()
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        receiver.cancel()
        await subscription.close()
        await runtime.streamer.release(session_id)
