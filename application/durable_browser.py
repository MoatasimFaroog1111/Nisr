from __future__ import annotations

import time

from application.browser_runtime import BrowserManager, BrowserSession
from domain.browser import BrowserControlOwner, BrowserControlState, BrowserEvent, BrowserState
from domain.browser_session import BrowserSessionSnapshot
from ports.browser import BrowserProvider
from ports.browser_session import BrowserSessionStorePort
from ports.realtime import BrowserEventPublisherPort


class DurableBrowserManager(BrowserManager):
    """BrowserManager extension that reconstructs logical sessions after process restart."""

    def __init__(
        self,
        provider: BrowserProvider,
        snapshots: BrowserSessionStorePort,
        *,
        viewport: dict[str, int],
        timeout_seconds: int = 1200,
        max_sessions: int = 8,
    ):
        super().__init__(provider, viewport=viewport, timeout_seconds=timeout_seconds, max_sessions=max_sessions)
        self._snapshots = snapshots
        self._recovery: dict[str, BrowserSessionSnapshot] = {}

    async def register(self, session_id: str, user_id: str) -> BrowserSession:
        existing = self._sessions.get(session_id)
        if existing:
            return await super().register(session_id, user_id)

        snapshot = self._snapshots.load(session_id)
        if snapshot and snapshot.expires_at_epoch <= time.time():
            self._snapshots.delete(session_id)
            snapshot = None
        if snapshot and snapshot.user_id != user_id:
            raise PermissionError("Browser session belongs to a different user")

        session = await super().register(session_id, user_id)
        if snapshot:
            session.task_id = snapshot.task_id
            session.owner = snapshot.owner
            session.control_state = (
                snapshot.control_state
                if snapshot.control_state != BrowserControlState.TRANSITIONING
                else BrowserControlState.USER_CONTROL
                if snapshot.owner == BrowserControlOwner.USER
                else BrowserControlState.AGENT_CONTROL
            )
            session.browser_started = snapshot.browser_started
            session.takeover_requested = snapshot.takeover_requested
            session.takeover_reason = snapshot.takeover_reason
            self._recovery[session_id] = snapshot
        return session

    async def ensure_browser(self, session: BrowserSession) -> BrowserState:
        if await self._provider.has_session(session.session_id):
            return await self._provider.get_tabs(session.session_id)

        snapshot = self._recovery.get(session.session_id)
        restore = getattr(self._provider, "restore_session", None)
        if snapshot and snapshot.browser_started and callable(restore):
            state = await restore(
                session.session_id,
                viewport=self._viewport,
                storage_state=snapshot.storage_state,
                tabs=snapshot.tabs,
                active_url=snapshot.current_url,
            )
            session.browser_started = True
            session.last_activity = time.monotonic()
            self._recovery.pop(session.session_id, None)
            state.reliability.update({
                "recovered_after_restart": True,
                "browser_state_changed": True,
                "cookies_local_storage_restored": True,
                "session_storage_restored": False,
                "exact_history_restored": False,
            })
            return state

        state = await super().ensure_browser(session)
        if snapshot:
            self._recovery.pop(session.session_id, None)
            state.reliability.update({
                "recovered_after_restart": True,
                "browser_state_changed": True,
                "cookies_local_storage_restored": False,
                "session_storage_restored": False,
                "exact_history_restored": False,
            })
        return state

    async def checkpoint(self, session_id: str, state: BrowserState | None = None) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        if state is None and session.browser_started and await self._provider.has_session(session_id):
            try:
                state = await self._provider.get_tabs(session_id)
            except Exception:
                state = None
        storage_state: dict = {}
        export = getattr(self._provider, "export_storage_state", None)
        if session.browser_started and callable(export) and await self._provider.has_session(session_id):
            try:
                storage_state = await export(session_id)
            except Exception:
                storage_state = {}

        snapshot = BrowserSessionSnapshot(
            session_id=session.session_id,
            user_id=session.user_id,
            task_id=session.task_id,
            owner=session.owner,
            control_state=session.control_state,
            browser_started=session.browser_started,
            takeover_requested=session.takeover_requested,
            takeover_reason=session.takeover_reason,
            current_url=state.url if state else "about:blank",
            tabs=state.tabs if state else [],
            storage_state=storage_state,
            updated_at_epoch=time.time(),
            expires_at_epoch=time.time() + self._timeout_seconds,
        )
        self._snapshots.save(snapshot)

    async def close(self, session_id: str, user_id: str | None = None) -> BrowserSession | None:
        session = await super().close(session_id, user_id)
        self._recovery.pop(session_id, None)
        self._snapshots.delete(session_id)
        return session

    async def cleanup_expired(self) -> list[BrowserSession]:
        closed = await super().cleanup_expired()
        self._snapshots.purge_expired(time.time())
        return closed


class CheckpointingBrowserEventPublisher:
    """Realtime publisher decorator that checkpoints durable browser state without changing BrowserService."""

    _CHECKPOINT_EVENTS = {
        "browser.started",
        "browser.loaded",
        "browser.url_changed",
        "browser.action",
        "browser.control_changed",
        "user_takeover_requested",
    }

    def __init__(
        self,
        inner: BrowserEventPublisherPort,
        manager: DurableBrowserManager,
    ):
        self._inner = inner
        self._manager = manager

    async def publish(self, event: BrowserEvent) -> None:
        await self._inner.publish(event)
        if event.type in self._CHECKPOINT_EVENTS:
            try:
                await self._manager.checkpoint(event.session_id)
            except Exception:
                # A checkpoint failure must not turn a healthy browser action into a task failure.
                pass
