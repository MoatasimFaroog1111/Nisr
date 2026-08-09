from __future__ import annotations

import asyncio

import pytest

from adapters.realtime.browser_events import InMemoryBrowserEventHub
from adapters.security.browser_tokens import BrowserSessionTokenService
from adapters.tools.browser import BrowserActionTool
from adapters.tools.registry import ToolRegistry
from application.browser_runtime import BrowserControlManager, BrowserManager, BrowserService
from domain.browser import BrowserControlError, BrowserFrame, BrowserState, BrowserTab


class FakeBrowserProvider:
    def __init__(self):
        self.states: dict[str, BrowserState] = {}
        self.user_clicks = 0

    async def create_session(self, session_id: str, *, viewport: dict[str, int]) -> BrowserState:
        state = BrowserState(
            session_id=session_id,
            viewport=dict(viewport),
            tabs=[BrowserTab(id="tab-1", index=0, active=True)],
        )
        self.states[session_id] = state
        return state.model_copy(deep=True)

    async def has_session(self, session_id: str) -> bool:
        return session_id in self.states

    def _get(self, session_id: str) -> BrowserState:
        if session_id not in self.states:
            raise KeyError(session_id)
        return self.states[session_id]

    async def navigate(self, session_id: str, url: str) -> BrowserState:
        state = self._get(session_id)
        state.url = url
        state.title = "Example"
        state.tabs[0].url = url
        state.tabs[0].title = "Example"
        return state.model_copy(deep=True)

    async def view(self, session_id: str) -> BrowserState:
        return self._get(session_id).model_copy(deep=True)

    async def click(self, session_id: str, selector: str) -> BrowserState:
        return await self.view(session_id)

    async def input(self, session_id: str, selector: str, value: str) -> BrowserState:
        return await self.view(session_id)

    async def press_key(self, session_id: str, key: str) -> BrowserState:
        return await self.view(session_id)

    async def scroll(self, session_id: str, delta_x: float, delta_y: float) -> BrowserState:
        return await self.view(session_id)

    async def select_option(self, session_id: str, selector: str, value: str) -> BrowserState:
        return await self.view(session_id)

    async def back(self, session_id: str) -> BrowserState:
        return await self.view(session_id)

    async def forward(self, session_id: str) -> BrowserState:
        return await self.view(session_id)

    async def refresh(self, session_id: str) -> BrowserState:
        return await self.view(session_id)

    async def get_tabs(self, session_id: str) -> BrowserState:
        return await self.view(session_id)

    async def switch_tab(self, session_id: str, tab_id: str) -> BrowserState:
        return await self.view(session_id)

    async def close_tab(self, session_id: str, tab_id: str) -> BrowserState:
        return await self.view(session_id)

    async def click_at(self, session_id: str, x: float, y: float) -> BrowserState:
        self.user_clicks += 1
        return await self.view(session_id)

    async def insert_text(self, session_id: str, text: str) -> BrowserState:
        return await self.view(session_id)

    async def capture_frame(self, session_id: str) -> BrowserFrame:
        self._get(session_id)
        return BrowserFrame(data_base64="ZmFrZQ==", width=1280, height=720)

    async def close_session(self, session_id: str) -> None:
        self.states.pop(session_id, None)

    async def close_all(self) -> None:
        self.states.clear()

    async def probe(self):
        return {"ok": True, "engine": "fake", "version": "1"}


def make_service():
    provider = FakeBrowserProvider()
    events = InMemoryBrowserEventHub()
    manager = BrowserManager(provider, viewport={"width": 1280, "height": 720}, timeout_seconds=300)
    service = BrowserService(manager, BrowserControlManager(), provider, events)
    return provider, events, manager, service


@pytest.mark.asyncio
async def test_takeover_prevents_simultaneous_agent_control_and_preserves_session():
    provider, _, _, service = make_service()
    await service.register_session("s1", "u1")
    navigated = await service.navigate("s1", "u1", "t1", "https://example.com")
    assert navigated.url == "https://example.com"

    taken = await service.take_control("s1", "u1")
    assert taken.owner.value == "user"
    assert taken.control_state.value == "USER_CONTROL"

    with pytest.raises(BrowserControlError) as exc:
        await service.click("s1", "u1", "t1", "#buy")
    assert exc.value.code == "BROWSER_CONTROLLED_BY_USER"

    user_state = await service.user_action("s1", "u1", "pointer.click", {"x": 20, "y": 30})
    assert user_state.url == "https://example.com"
    assert provider.user_clicks == 1

    returned = await service.return_control("s1", "u1")
    assert returned.owner.value == "agent"
    assert returned.control_state.value == "AGENT_CONTROL"
    assert returned.url == "https://example.com"
    assert await provider.has_session("s1")


@pytest.mark.asyncio
async def test_browser_sessions_are_isolated_by_user_id():
    _, _, manager, service = make_service()
    await service.register_session("same-session", "user-a")
    with pytest.raises(PermissionError):
        await service.register_session("same-session", "user-b")
    with pytest.raises(PermissionError):
        manager.get("same-session", "user-b")


@pytest.mark.asyncio
async def test_sensitive_page_requests_takeover_without_exposing_secret():
    provider, events, _, service = make_service()
    await service.register_session("sensitive", "u1")
    await service.navigate("sensitive", "u1", "task", "https://example.com/login")
    provider.states["sensitive"].sensitive_signals = ["otp_or_2fa"]
    subscription = await events.subscribe("sensitive")
    try:
        state = await service.view("sensitive", "u1", "task")
        assert state.sensitive_signals == ["otp_or_2fa"]
        found = None
        for _ in range(6):
            event = await asyncio.wait_for(subscription.receive(), timeout=1)
            if event.type == "user_takeover_requested":
                found = event
                break
        assert found is not None
        assert found.data["reason"] == "otp_or_2fa"
    finally:
        await subscription.close()


def test_browser_input_arguments_are_redacted_before_audit_or_state_storage():
    _, _, _, service = make_service()
    registry = ToolRegistry()
    registry.register(BrowserActionTool("input", service))
    safe = registry.sanitize("browser.input", {"selector": "#password", "value": "super-secret"})
    assert safe["selector"] == "#password"
    assert safe["value"] == "[REDACTED]"
    assert "super-secret" not in str(safe)


def test_browser_session_tokens_are_bound_to_user_and_session():
    tokens = BrowserSessionTokenService("unit-test-secret", ttl_seconds=300)
    token = tokens.issue(session_id="s1", user_id="u1")
    assert tokens.verify(token, session_id="s1", user_id="u1")
    assert tokens.verify(token, session_id="s2", user_id="u1") is None
    assert tokens.verify(token, session_id="s1", user_id="u2") is None
    assert tokens.verify("invalid", session_id="s1", user_id="u1") is None
