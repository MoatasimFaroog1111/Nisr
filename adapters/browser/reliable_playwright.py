from __future__ import annotations

import hashlib
from typing import Any, Awaitable, Callable

from adapters.browser.playwright_provider import PlaywrightBrowserProvider, _PlaywrightSession
from domain.browser import BrowserState, BrowserTab, SensitiveBrowserOperation
from domain.browser_reliability import BrowserReliabilityPolicy


class ReliablePlaywrightBrowserProvider(PlaywrightBrowserProvider):
    """Production Playwright adapter with resilient location, evidence, and optional durable recovery."""

    def __init__(self, *, reliability: BrowserReliabilityPolicy | None = None, launch_args: list[str] | None = None):
        super().__init__(launch_args=launch_args)
        self._reliability = reliability or BrowserReliabilityPolicy()

    async def export_storage_state(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        return dict(await session.context.storage_state())

    async def restore_session(
        self,
        session_id: str,
        *,
        viewport: dict[str, int],
        storage_state: dict[str, Any],
        tabs: list[BrowserTab],
        active_url: str,
    ) -> BrowserState:
        if await self.has_session(session_id):
            return await self.view(session_id)
        self._sessions.pop(session_id, None)
        await self._ensure_runtime()
        context = await self._browser.new_context(
            viewport={"width": int(viewport["width"]), "height": int(viewport["height"])},
            accept_downloads=False,
            storage_state=storage_state or None,
        )
        await context.route("**/*", self._route_guard)

        restored_pages: list[tuple[Any, BrowserTab | None]] = []
        candidates = tabs[:8] if tabs else []
        if not candidates:
            candidates = [BrowserTab(id="recovered", index=0, url=active_url or "about:blank", active=True)]
        for tab in candidates:
            page = await context.new_page()
            restored_pages.append((page, tab))

        active_page = restored_pages[0][0]
        session = _PlaywrightSession(context=context, active_page=active_page, viewport=dict(viewport))
        self._sessions[session_id] = session
        for page, tab in restored_pages:
            if tab and tab.id:
                session.tab_ids[id(page)] = tab.id
            else:
                self._tab_id(session, page)
            target = tab.url if tab else active_url
            if target and target != "about:blank" and self._url_allowed(target):
                try:
                    await page.goto(target, wait_until="domcontentloaded", timeout=20_000)
                except Exception:
                    pass
            if tab and (tab.active or (active_url and tab.url == active_url)):
                active_page = page
        session.active_page = active_page
        try:
            await active_page.bring_to_front()
        except Exception:
            pass
        state = await self._state(session_id, include_interactables=False)
        state.reliability.update({
            "recovered_after_restart": True,
            "cookies_local_storage_restored": bool(storage_state),
            "session_storage_restored": False,
            "exact_history_restored": False,
        })
        return state

    async def _safe_call(self, action: str, operation: Callable[[], Awaitable[BrowserState]]) -> BrowserState:
        last_error: Exception | None = None
        for attempt in range(1, self._reliability.max_attempts(action) + 1):
            try:
                state = await operation()
                state.reliability.update({
                    "action": action,
                    "attempt": attempt,
                    "safe_retry": self._reliability.safe_to_retry(action),
                })
                return state
            except Exception as exc:
                last_error = exc
                if attempt >= self._reliability.max_attempts(action):
                    raise
        assert last_error is not None
        raise last_error

    @staticmethod
    async def _wait_dom(page: Any) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            pass

    @staticmethod
    def _semantic_expression(selector: str) -> tuple[str, str, str | None] | None:
        raw = selector.strip()
        if raw.startswith("text="):
            return ("text", raw[5:], None)
        if raw.startswith("label="):
            return ("label", raw[6:], None)
        if raw.startswith("testid="):
            return ("testid", raw[7:], None)
        if raw.startswith("role="):
            value = raw[5:]
            role, _, name = value.partition("|name=")
            return ("role", role, name or None)
        return None

    async def _resolve_locator(self, page: Any, selector: str):
        semantic = self._semantic_expression(selector)
        if semantic:
            kind, value, name = semantic
            if kind == "text":
                return page.get_by_text(value, exact=False).first, "text"
            if kind == "label":
                return page.get_by_label(value, exact=False).first, "label"
            if kind == "testid":
                return page.get_by_test_id(value).first, "testid"
            return page.get_by_role(value, name=name, exact=False).first, "role"
        try:
            locator = page.locator(selector)
            if await locator.count() > 0:
                return locator.first, "css"
        except Exception:
            pass
        text = selector.strip()
        for role in ("link", "button", "textbox", "option"):
            try:
                candidate = page.get_by_role(role, name=text, exact=False)
                if await candidate.count() > 0:
                    return candidate.first, f"role:{role}"
            except Exception:
                continue
        candidate = page.get_by_text(text, exact=False)
        if await candidate.count() > 0:
            return candidate.first, "text-fallback"
        raise ValueError(f"Browser element could not be resolved: {selector[:160]}")

    async def _verified_state(self, session_id: str, *, action: str, strategy: str = "", before_url: str = "") -> BrowserState:
        session, page = await self._active(session_id)
        state = await self._state(session_id, include_interactables=False)
        try:
            ready_state = await page.evaluate("document.readyState")
        except Exception:
            ready_state = "unknown"
        screenshot_hash = None
        try:
            image = await page.screenshot(type="jpeg", quality=35, full_page=False, animations="disabled", caret="hide")
            screenshot_hash = hashlib.sha256(image).hexdigest()[:20]
        except Exception:
            pass
        state.reliability.update({
            "action": action,
            "verified": True,
            "locator_strategy": strategy or None,
            "dom_ready_state": ready_state,
            "screenshot_sha256": screenshot_hash,
            "url_changed": bool(before_url and state.url != before_url),
            "tab_count": len([p for p in session.context.pages if not p.is_closed()]),
        })
        return state

    async def navigate(self, session_id: str, url: str) -> BrowserState:
        async def operation() -> BrowserState:
            before = ""
            try:
                _, page = await self._active(session_id)
                before = page.url
            except Exception:
                pass
            await super(ReliablePlaywrightBrowserProvider, self).navigate(session_id, url)
            return await self._verified_state(session_id, action="navigate", before_url=before)
        return await self._safe_call("navigate", operation)

    async def view(self, session_id: str) -> BrowserState:
        async def operation() -> BrowserState:
            state = await super(ReliablePlaywrightBrowserProvider, self).view(session_id)
            for row in state.interactables:
                text = str(row.get("text") or "").strip()
                tag = str(row.get("tag") or "").lower()
                if text and tag in {"a", "button"}:
                    role = "link" if tag == "a" else "button"
                    row["semantic_selector"] = f"role={role}|name={text[:120]}"
                elif text and tag in {"input", "textarea"}:
                    row["semantic_selector"] = f"label={text[:120]}"
            state.reliability.update({"action": "view", "verified": True})
            return state
        return await self._safe_call("view", operation)

    async def click(self, session_id: str, selector: str) -> BrowserState:
        session, page = await self._active(session_id)
        await self._wait_dom(page)
        before_url = page.url
        before_pages = {id(candidate) for candidate in session.context.pages if not candidate.is_closed()}
        locator, strategy = await self._resolve_locator(page, selector)
        await locator.wait_for(state="visible", timeout=8_000)
        fingerprint = await locator.evaluate(
            """el => [el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title'),
            el.getAttribute('name'), el.id, el.getAttribute('value')].filter(Boolean).join(' ').toLowerCase().slice(0, 1000)"""
        )
        if any(marker in str(fingerprint) for marker in self._SENSITIVE_CLICK_MARKERS):
            raise SensitiveBrowserOperation("Payment, banking, identity, or security confirmation requires user control")
        await locator.click(timeout=12_000)
        try:
            await page.wait_for_timeout(180)
        except Exception:
            pass
        pages = [candidate for candidate in session.context.pages if not candidate.is_closed()]
        new_pages = [candidate for candidate in pages if id(candidate) not in before_pages]
        if new_pages:
            session.active_page = new_pages[-1]
            try:
                await session.active_page.bring_to_front()
                await session.active_page.wait_for_load_state("domcontentloaded", timeout=8_000)
            except Exception:
                pass
        return await self._verified_state(session_id, action="click", strategy=strategy, before_url=before_url)

    async def input(self, session_id: str, selector: str, value: str) -> BrowserState:
        _, page = await self._active(session_id)
        await self._wait_dom(page)
        before_url = page.url
        locator, strategy = await self._resolve_locator(page, selector)
        info = await locator.evaluate(
            """el => ({type:(el.getAttribute('type')||'').toLowerCase(), autocomplete:(el.getAttribute('autocomplete')||'').toLowerCase(),
            name:(el.getAttribute('name')||'').toLowerCase(), id:(el.id||'').toLowerCase(), aria:(el.getAttribute('aria-label')||'').toLowerCase(),
            placeholder:(el.getAttribute('placeholder')||'').toLowerCase()})"""
        )
        fingerprint = " ".join(str(info.get(k, "")) for k in info)
        if info.get("type") == "password" or any(marker in fingerprint for marker in (
            "current-password", "new-password", "one-time-code", " otp", "2fa", "mfa",
            "verification code", "passcode", "cc-number", "cc-csc", "cvv", "cvc", "card number",
        )):
            raise SensitiveBrowserOperation("This field contains credentials, OTP, payment, or security data")
        await locator.fill(value)
        return await self._verified_state(session_id, action="input", strategy=strategy, before_url=before_url)

    async def select_option(self, session_id: str, selector: str, value: str) -> BrowserState:
        _, page = await self._active(session_id)
        await self._wait_dom(page)
        before_url = page.url
        locator, strategy = await self._resolve_locator(page, selector)
        await locator.select_option(value)
        return await self._verified_state(session_id, action="selectOption", strategy=strategy, before_url=before_url)

    async def back(self, session_id: str) -> BrowserState:
        return await self._safe_call("back", lambda: super(ReliablePlaywrightBrowserProvider, self).back(session_id))

    async def forward(self, session_id: str) -> BrowserState:
        return await self._safe_call("forward", lambda: super(ReliablePlaywrightBrowserProvider, self).forward(session_id))

    async def refresh(self, session_id: str) -> BrowserState:
        return await self._safe_call("refresh", lambda: super(ReliablePlaywrightBrowserProvider, self).refresh(session_id))

    async def get_tabs(self, session_id: str) -> BrowserState:
        return await self._safe_call("getTabs", lambda: super(ReliablePlaywrightBrowserProvider, self).get_tabs(session_id))

    async def switch_tab(self, session_id: str, tab_id: str) -> BrowserState:
        return await self._safe_call("switchTab", lambda: super(ReliablePlaywrightBrowserProvider, self).switch_tab(session_id, tab_id))
