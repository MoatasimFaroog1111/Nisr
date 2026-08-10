from __future__ import annotations

from pathlib import Path

import pytest

from adapters.storage.browser_session_sqlite import SqliteBrowserSessionStore
from application.durable_browser import DurableBrowserManager
from domain.browser import BrowserControlOwner, BrowserControlState, BrowserFrame, BrowserState, BrowserTab


class PersistentFakeBrowserProvider:
    def __init__(self):
        self.sessions: dict[str, BrowserState] = {}
        self.storage: dict[str, dict] = {}
        self.restore_calls: list[dict] = []

    async def create_session(self, session_id, *, viewport):
        state = BrowserState(session_id=session_id, viewport=viewport)
        self.sessions[session_id] = state
        self.storage[session_id] = {"cookies": [{"name": "auth", "value": "token"}], "origins": []}
        return state

    async def has_session(self, session_id): return session_id in self.sessions
    async def get_tabs(self, session_id): return self.sessions[session_id].model_copy(deep=True)
    async def view(self, session_id): return await self.get_tabs(session_id)
    async def navigate(self, session_id, url):
        state = self.sessions[session_id]
        state.url = url
        state.tabs = [BrowserTab(id="tab1", index=0, url=url, title="Recovered", active=True)]
        return state.model_copy(deep=True)
    async def export_storage_state(self, session_id): return dict(self.storage[session_id])

    async def restore_session(self, session_id, *, viewport, storage_state, tabs, active_url):
        self.restore_calls.append({"session_id": session_id, "storage_state": storage_state, "tabs": tabs, "active_url": active_url})
        state = BrowserState(
            session_id=session_id,
            viewport=viewport,
            url=active_url,
            tabs=tabs,
            reliability={"recovered_after_restart": True},
        )
        self.sessions[session_id] = state
        self.storage[session_id] = dict(storage_state)
        return state.model_copy(deep=True)

    async def close_session(self, session_id): self.sessions.pop(session_id, None)
    async def close_all(self): self.sessions.clear()
    async def back(self, session_id): return await self.get_tabs(session_id)
    async def forward(self, session_id): return await self.get_tabs(session_id)
    async def refresh(self, session_id): return await self.get_tabs(session_id)
    async def switch_tab(self, session_id, tab_id): return await self.get_tabs(session_id)
    async def close_tab(self, session_id, tab_id): return await self.get_tabs(session_id)
    async def click(self, session_id, selector): return await self.get_tabs(session_id)
    async def input(self, session_id, selector, value): return await self.get_tabs(session_id)
    async def press_key(self, session_id, key): return await self.get_tabs(session_id)
    async def scroll(self, session_id, delta_x, delta_y): return await self.get_tabs(session_id)
    async def select_option(self, session_id, selector, value): return await self.get_tabs(session_id)
    async def click_at(self, session_id, x, y): return await self.get_tabs(session_id)
    async def insert_text(self, session_id, text): return await self.get_tabs(session_id)
    async def capture_frame(self, session_id): return BrowserFrame(data_base64="", width=1, height=1)
    async def probe(self): return {"ok": True}


@pytest.mark.asyncio
async def test_browser_session_recovers_same_owner_url_tabs_and_storage_after_process_replacement(tmp_path: Path):
    store = SqliteBrowserSessionStore(tmp_path / "sessions.sqlite3")
    provider1 = PersistentFakeBrowserProvider()
    manager1 = DurableBrowserManager(provider1, store, viewport={"width": 1280, "height": 720}, timeout_seconds=1200)

    session1 = await manager1.register("session-1", "user-1")
    await manager1.ensure_browser(session1)
    state1 = await provider1.navigate("session-1", "https://example.test/account")
    session1.owner = BrowserControlOwner.USER
    session1.control_state = BrowserControlState.USER_CONTROL
    session1.task_id = "task-7"
    await manager1.checkpoint("session-1", state1)
    await manager1.close_all()  # simulates process/runtime shutdown; snapshot must remain

    provider2 = PersistentFakeBrowserProvider()
    manager2 = DurableBrowserManager(provider2, store, viewport={"width": 1280, "height": 720}, timeout_seconds=1200)
    session2 = await manager2.register("session-1", "user-1")
    recovered = await manager2.ensure_browser(session2)

    assert session2.owner == BrowserControlOwner.USER
    assert session2.control_state == BrowserControlState.USER_CONTROL
    assert session2.task_id == "task-7"
    assert recovered.url == "https://example.test/account"
    assert recovered.tabs[0].id == "tab1"
    assert provider2.restore_calls[0]["storage_state"]["cookies"][0]["name"] == "auth"
    assert recovered.reliability["recovered_after_restart"] is True
    assert recovered.reliability["session_storage_restored"] is False
    assert recovered.reliability["exact_history_restored"] is False


@pytest.mark.asyncio
async def test_recovered_session_still_enforces_user_ownership(tmp_path: Path):
    store = SqliteBrowserSessionStore(tmp_path / "sessions.sqlite3")
    provider = PersistentFakeBrowserProvider()
    manager = DurableBrowserManager(provider, store, viewport={"width": 800, "height": 600})
    session = await manager.register("s", "owner")
    await manager.ensure_browser(session)
    await manager.checkpoint("s", await provider.get_tabs("s"))
    await manager.close_all()

    replacement = DurableBrowserManager(PersistentFakeBrowserProvider(), store, viewport={"width": 800, "height": 600})
    with pytest.raises(PermissionError):
        await replacement.register("s", "other-user")


def test_sqlite_snapshot_purge_removes_expired_rows(tmp_path: Path):
    from domain.browser_session import BrowserSessionSnapshot

    store = SqliteBrowserSessionStore(tmp_path / "sessions.sqlite3")
    store.save(BrowserSessionSnapshot(session_id="expired", user_id="u", expires_at_epoch=1.0))
    assert store.load("expired") is not None
    assert store.purge_expired(2.0) == 1
    assert store.load("expired") is None
