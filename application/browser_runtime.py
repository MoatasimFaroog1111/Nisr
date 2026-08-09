from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from domain.browser import (
    BrowserControlError,
    BrowserControlOwner,
    BrowserControlState,
    BrowserEvent,
    BrowserFrame,
    BrowserState,
    SensitiveBrowserOperation,
)
from ports.browser import BrowserProvider
from ports.realtime import BrowserEventPublisherPort


@dataclass(slots=True)
class BrowserSession:
    """Logical session metadata; Playwright objects stay inside BrowserProvider."""

    session_id: str
    user_id: str
    task_id: str | None = None
    owner: BrowserControlOwner = BrowserControlOwner.AGENT
    control_state: BrowserControlState = BrowserControlState.AGENT_CONTROL
    browser_started: bool = False
    takeover_requested: bool = False
    takeover_reason: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class BrowserManager:
    """Owns logical browser sessions and delegates browser mechanics to BrowserProvider."""

    def __init__(
        self,
        provider: BrowserProvider,
        *,
        viewport: dict[str, int],
        timeout_seconds: int = 1200,
        max_sessions: int = 8,
    ):
        self._provider = provider
        self._viewport = dict(viewport)
        self._timeout_seconds = max(60, int(timeout_seconds))
        self._max_sessions = max(1, int(max_sessions))
        self._sessions: dict[str, BrowserSession] = {}
        self._manager_lock = asyncio.Lock()

    async def register(self, session_id: str, user_id: str) -> BrowserSession:
        async with self._manager_lock:
            existing = self._sessions.get(session_id)
            if existing:
                if existing.user_id != user_id:
                    raise PermissionError("Browser session belongs to a different user")
                existing.last_activity = time.monotonic()
                return existing
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError("Browser session capacity reached; close an existing session first")
            session = BrowserSession(session_id=session_id, user_id=user_id)
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str, user_id: str) -> BrowserSession:
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError("Unknown browser session")
        if session.user_id != user_id:
            raise PermissionError("Browser session belongs to a different user")
        session.last_activity = time.monotonic()
        return session

    async def ensure_browser(self, session: BrowserSession) -> BrowserState:
        if not session.browser_started or not await self._provider.has_session(session.session_id):
            state = await self._provider.create_session(session.session_id, viewport=self._viewport)
            session.browser_started = True
            session.last_activity = time.monotonic()
            return state
        return await self._provider.get_tabs(session.session_id)

    async def bind_task(self, session: BrowserSession, task_id: str | None) -> None:
        if task_id:
            session.task_id = task_id
        session.last_activity = time.monotonic()

    async def close(self, session_id: str, user_id: str | None = None) -> BrowserSession | None:
        async with self._manager_lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            if user_id is not None and session.user_id != user_id:
                raise PermissionError("Browser session belongs to a different user")
            self._sessions.pop(session_id, None)
        if session.browser_started:
            await self._provider.close_session(session_id)
        return session

    async def close_all(self) -> None:
        async with self._manager_lock:
            self._sessions.clear()
        await self._provider.close_all()

    async def cleanup_expired(self) -> list[BrowserSession]:
        now = time.monotonic()
        expired = [
            session
            for session in list(self._sessions.values())
            if now - session.last_activity >= self._timeout_seconds
        ]
        closed: list[BrowserSession] = []
        for session in expired:
            removed = await self.close(session.session_id, session.user_id)
            if removed:
                closed.append(removed)
        return closed


class BrowserControlManager:
    """Serializes ownership transitions so agent and user never control concurrently."""

    async def require(self, session: BrowserSession, actor: BrowserControlOwner) -> None:
        if session.control_state == BrowserControlState.TRANSITIONING:
            raise BrowserControlError("BROWSER_CONTROL_TRANSITIONING", "Browser control is transitioning")
        if session.owner != actor:
            code = "BROWSER_CONTROLLED_BY_USER" if session.owner == BrowserControlOwner.USER else "BROWSER_CONTROLLED_BY_AGENT"
            raise BrowserControlError(code, f"Browser is currently controlled by {session.owner.value}")

    async def take_control(self, session: BrowserSession) -> None:
        if session.owner == BrowserControlOwner.USER:
            session.control_state = BrowserControlState.USER_CONTROL
            return
        session.control_state = BrowserControlState.TRANSITIONING
        await asyncio.sleep(0)
        session.owner = BrowserControlOwner.USER
        session.control_state = BrowserControlState.USER_CONTROL
        session.last_activity = time.monotonic()

    async def return_control(self, session: BrowserSession) -> None:
        if session.owner == BrowserControlOwner.AGENT:
            session.control_state = BrowserControlState.AGENT_CONTROL
            return
        session.control_state = BrowserControlState.TRANSITIONING
        await asyncio.sleep(0)
        session.owner = BrowserControlOwner.AGENT
        session.control_state = BrowserControlState.AGENT_CONTROL
        session.takeover_requested = False
        session.takeover_reason = None
        session.last_activity = time.monotonic()


class BrowserService:
    """Application-facing browser use-case service. It never imports Playwright or WebSocket."""

    def __init__(
        self,
        manager: BrowserManager,
        control: BrowserControlManager,
        provider: BrowserProvider,
        events: BrowserEventPublisherPort,
    ):
        self._manager = manager
        self._control = control
        self._provider = provider
        self._events = events

    async def register_session(self, session_id: str, user_id: str) -> BrowserSession:
        return await self._manager.register(session_id, user_id)

    async def _publish(
        self,
        event_type: str,
        session: BrowserSession,
        *,
        actor: str | None = None,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        await self._events.publish(
            BrowserEvent(
                type=event_type,
                session_id=session.session_id,
                task_id=session.task_id,
                actor=actor,
                message=message,
                data=data or {},
            )
        )

    @staticmethod
    def _decorate(state: BrowserState, session: BrowserSession) -> BrowserState:
        state.task_id = session.task_id
        state.owner = session.owner
        state.control_state = session.control_state
        return state

    @staticmethod
    def _state_event_data(state: BrowserState) -> dict[str, Any]:
        return {
            "url": state.url,
            "title": state.title,
            "loading": state.loading,
            "owner": state.owner.value,
            "control_state": state.control_state.value,
            "tabs": [tab.model_dump(mode="json") for tab in state.tabs],
        }

    async def _ensure(self, session: BrowserSession) -> BrowserState:
        was_started = session.browser_started and await self._provider.has_session(session.session_id)
        state = await self._manager.ensure_browser(session)
        state = self._decorate(state, session)
        if not was_started:
            await self._publish(
                "browser.started",
                session,
                actor="system",
                message="Browser started",
                data={"viewport": state.viewport, **self._state_event_data(state)},
            )
        return state

    async def _agent_action(
        self,
        session_id: str,
        user_id: str,
        task_id: str | None,
        action_name: str,
        operation: Callable[[], Awaitable[BrowserState]],
        *,
        message: str,
        event_data: dict[str, Any] | None = None,
    ) -> BrowserState:
        session = self._manager.get(session_id, user_id)
        async with session.lock:
            await self._manager.bind_task(session, task_id)
            await self._control.require(session, BrowserControlOwner.AGENT)
            await self._ensure(session)
            await self._publish(
                "browser.action",
                session,
                actor="agent",
                message=message,
                data={"action": action_name, **(event_data or {})},
            )
            try:
                state = await operation()
            except SensitiveBrowserOperation as exc:
                await self.request_user_takeover(session_id, user_id, str(exc), task_id=task_id, already_locked=True)
                raise
            except Exception as exc:
                state_changed = False
                recovery_error = None
                try:
                    if session.browser_started and not await self._provider.has_session(session.session_id):
                        recovered = await self._manager.ensure_browser(session)
                        self._decorate(recovered, session)
                        state_changed = True
                except Exception as recovery_exc:
                    recovery_error = type(recovery_exc).__name__
                await self._publish(
                    "browser.error",
                    session,
                    actor="agent",
                    message="Browser action failed",
                    data={
                        "action": action_name,
                        "error_type": type(exc).__name__,
                        "browser_state_changed": state_changed,
                        "recovery_error_type": recovery_error,
                    },
                )
                raise
            session.last_activity = time.monotonic()
            state = self._decorate(state, session)
            await self._publish(
                "browser.url_changed",
                session,
                actor="agent",
                message=state.url,
                data=self._state_event_data(state),
            )
            return state

    async def navigate(self, session_id: str, user_id: str, task_id: str | None, url: str) -> BrowserState:
        session = self._manager.get(session_id, user_id)
        await self._publish(
            "browser.navigating",
            session,
            actor="agent",
            message=f"Opening {url}",
            data={"url": url},
        )
        state = await self._agent_action(
            session_id, user_id, task_id, "navigate",
            lambda: self._provider.navigate(session_id, url),
            message="Navigating browser",
            event_data={"url": url},
        )
        await self._publish(
            "browser.loaded",
            self._manager.get(session_id, user_id),
            actor="agent",
            message="Page loaded",
            data=self._state_event_data(state),
        )
        return state

    async def view(self, session_id: str, user_id: str, task_id: str | None) -> BrowserState:
        state = await self._agent_action(
            session_id, user_id, task_id, "view",
            lambda: self._provider.view(session_id),
            message="Reading page",
        )
        if state.sensitive_signals:
            reason = ", ".join(state.sensitive_signals)
            await self.request_user_takeover(session_id, user_id, reason, task_id=task_id)
        return state

    async def click(self, session_id: str, user_id: str, task_id: str | None, selector: str) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "click",
            lambda: self._provider.click(session_id, selector),
            message="Clicking page element",
            event_data={"selector": selector},
        )

    async def input(self, session_id: str, user_id: str, task_id: str | None, selector: str, value: str) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "input",
            lambda: self._provider.input(session_id, selector, value),
            message="Typing into page",
            event_data={"selector": selector, "characters": len(value)},
        )

    async def press_key(self, session_id: str, user_id: str, task_id: str | None, key: str) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "pressKey",
            lambda: self._provider.press_key(session_id, key),
            message=f"Pressing {key}",
            event_data={"key": key},
        )

    async def scroll(self, session_id: str, user_id: str, task_id: str | None, delta_x: float, delta_y: float) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "scroll",
            lambda: self._provider.scroll(session_id, delta_x, delta_y),
            message="Scrolling page",
            event_data={"delta_x": delta_x, "delta_y": delta_y},
        )

    async def select_option(self, session_id: str, user_id: str, task_id: str | None, selector: str, value: str) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "selectOption",
            lambda: self._provider.select_option(session_id, selector, value),
            message="Selecting an option",
            event_data={"selector": selector},
        )

    async def back(self, session_id: str, user_id: str, task_id: str | None) -> BrowserState:
        return await self._agent_action(session_id, user_id, task_id, "back", lambda: self._provider.back(session_id), message="Going back")

    async def forward(self, session_id: str, user_id: str, task_id: str | None) -> BrowserState:
        return await self._agent_action(session_id, user_id, task_id, "forward", lambda: self._provider.forward(session_id), message="Going forward")

    async def refresh(self, session_id: str, user_id: str, task_id: str | None) -> BrowserState:
        return await self._agent_action(session_id, user_id, task_id, "refresh", lambda: self._provider.refresh(session_id), message="Refreshing page")

    async def get_tabs(self, session_id: str, user_id: str, task_id: str | None) -> BrowserState:
        return await self._agent_action(session_id, user_id, task_id, "getTabs", lambda: self._provider.get_tabs(session_id), message="Reading browser tabs")

    async def switch_tab(self, session_id: str, user_id: str, task_id: str | None, tab_id: str) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "switchTab",
            lambda: self._provider.switch_tab(session_id, tab_id),
            message="Switching browser tab",
            event_data={"tab_id": tab_id},
        )

    async def close_tab(self, session_id: str, user_id: str, task_id: str | None, tab_id: str) -> BrowserState:
        return await self._agent_action(
            session_id, user_id, task_id, "closeTab",
            lambda: self._provider.close_tab(session_id, tab_id),
            message="Closing browser tab",
            event_data={"tab_id": tab_id},
        )

    async def request_user_takeover(
        self,
        session_id: str,
        user_id: str,
        reason: str,
        *,
        task_id: str | None = None,
        already_locked: bool = False,
    ) -> None:
        session = self._manager.get(session_id, user_id)

        async def mark() -> None:
            await self._manager.bind_task(session, task_id)
            session.takeover_requested = True
            session.takeover_reason = reason
            await self._publish(
                "user_takeover_requested",
                session,
                actor="agent",
                message="Your input is required to continue this step.",
                data={"reason": reason},
            )

        if already_locked:
            await mark()
        else:
            async with session.lock:
                await mark()

    async def take_control(self, session_id: str, user_id: str) -> BrowserState:
        session = self._manager.get(session_id, user_id)
        async with session.lock:
            await self._ensure(session)
            await self._control.take_control(session)
            state = self._decorate(await self._provider.view(session_id), session)
            await self._publish(
                "browser.control_changed",
                session,
                actor="user",
                message="You have control of the browser.",
                data=self._state_event_data(state),
            )
            return state

    async def return_control(self, session_id: str, user_id: str) -> BrowserState:
        session = self._manager.get(session_id, user_id)
        async with session.lock:
            await self._ensure(session)
            await self._control.require(session, BrowserControlOwner.USER)
            await self._control.return_control(session)
            state = self._decorate(await self._provider.view(session_id), session)
            await self._publish(
                "browser.control_changed",
                session,
                actor="user",
                message="Control returned to agent.",
                data=self._state_event_data(state),
            )
            return state

    async def user_action(self, session_id: str, user_id: str, action: str, payload: dict[str, Any]) -> BrowserState:
        session = self._manager.get(session_id, user_id)
        async with session.lock:
            await self._ensure(session)
            await self._control.require(session, BrowserControlOwner.USER)
            if action == "pointer.click":
                state = await self._provider.click_at(session_id, float(payload["x"]), float(payload["y"]))
                event_data = {"action": action, "x": float(payload["x"]), "y": float(payload["y"])}
            elif action == "text.insert":
                text = str(payload.get("text", ""))
                state = await self._provider.insert_text(session_id, text)
                event_data = {"action": action, "characters": len(text)}
            elif action == "key.press":
                key = str(payload.get("key", ""))
                state = await self._provider.press_key(session_id, key)
                event_data = {"action": action, "key": key}
            elif action == "scroll":
                dx, dy = float(payload.get("delta_x", 0)), float(payload.get("delta_y", 0))
                state = await self._provider.scroll(session_id, dx, dy)
                event_data = {"action": action, "delta_x": dx, "delta_y": dy}
            elif action == "navigate":
                url = str(payload.get("url", ""))
                state = await self._provider.navigate(session_id, url)
                event_data = {"action": action, "url": url}
            elif action == "back":
                state = await self._provider.back(session_id)
                event_data = {"action": action}
            elif action == "forward":
                state = await self._provider.forward(session_id)
                event_data = {"action": action}
            elif action == "refresh":
                state = await self._provider.refresh(session_id)
                event_data = {"action": action}
            elif action == "switchTab":
                tab_id = str(payload.get("tab_id", ""))
                state = await self._provider.switch_tab(session_id, tab_id)
                event_data = {"action": action, "tab_id": tab_id}
            elif action == "closeTab":
                tab_id = str(payload.get("tab_id", ""))
                state = await self._provider.close_tab(session_id, tab_id)
                event_data = {"action": action, "tab_id": tab_id}
            else:
                raise ValueError("Unsupported user browser action")
            session.last_activity = time.monotonic()
            state = self._decorate(state, session)
            await self._publish(
                "browser.action",
                session,
                actor="user",
                message="User interacted with browser",
                data=event_data,
            )
            await self._publish(
                "browser.url_changed",
                session,
                actor="user",
                message=state.url,
                data=self._state_event_data(state),
            )
            return state

    async def get_state(self, session_id: str, user_id: str) -> BrowserState:
        session = self._manager.get(session_id, user_id)
        async with session.lock:
            await self._ensure(session)
            return self._decorate(await self._provider.view(session_id), session)

    async def capture_frame(self, session_id: str, user_id: str) -> BrowserFrame | None:
        session = self._manager.get(session_id, user_id)
        if not session.browser_started or not await self._provider.has_session(session_id):
            return None
        async with session.lock:
            frame = await self._provider.capture_frame(session_id)
            session.last_activity = time.monotonic()
            return frame

    async def publish_frame(self, session_id: str, user_id: str) -> None:
        frame = await self.capture_frame(session_id, user_id)
        if not frame:
            return
        session = self._manager.get(session_id, user_id)
        await self._publish(
            "browser.frame",
            session,
            actor="system",
            data={
                "mime_type": frame.mime_type,
                "data_base64": frame.data_base64,
                "width": frame.width,
                "height": frame.height,
                "captured_at": frame.captured_at,
            },
        )

    async def close_session(self, session_id: str, user_id: str) -> None:
        session = await self._manager.close(session_id, user_id)
        if session:
            await self._publish("browser.closed", session, actor="system", message="Browser closed")

    async def cleanup_expired(self) -> None:
        for session in await self._manager.cleanup_expired():
            await self._publish(
                "browser.closed",
                session,
                actor="system",
                message="Browser session closed after inactivity timeout",
                data={"reason": "timeout"},
            )
