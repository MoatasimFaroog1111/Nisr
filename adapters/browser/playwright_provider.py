from __future__ import annotations

import base64
import ipaddress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from domain.browser import BrowserFrame, BrowserState, BrowserTab, SensitiveBrowserOperation


@dataclass(slots=True)
class _PlaywrightSession:
    context: Any
    active_page: Any
    viewport: dict[str, int]
    loading: bool = False
    tab_ids: dict[int, str] = field(default_factory=dict)


class PlaywrightBrowserProvider:
    """Playwright implementation hidden behind BrowserProvider."""

    _BLOCKED_HOSTS = {
        "localhost",
        "host.docker.internal",
        "gateway.docker.internal",
        "metadata.google.internal",
        "metadata.aws.internal",
    }
    _SENSITIVE_CLICK_MARKERS = (
        "confirm payment",
        "submit payment",
        "pay now",
        "place order",
        "complete purchase",
        "confirm purchase",
        "send money",
        "transfer money",
        "confirm transfer",
        "verify identity",
        "security verification",
        "bank authentication",
    )

    def __init__(self, *, launch_args: list[str] | None = None):
        self._launch_args = launch_args or ["--disable-dev-shm-usage"]
        self._playwright = None
        self._browser = None
        self._sessions: dict[str, _PlaywrightSession] = {}

    def _connected(self) -> bool:
        try:
            return bool(self._browser and self._browser.is_connected())
        except Exception:
            return False

    async def _discard_runtime(self) -> None:
        self._sessions.clear()
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass

    async def _ensure_runtime(self) -> None:
        if self._connected():
            return
        if self._browser or self._playwright:
            await self._discard_runtime()
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Browser automation is not installed. Install the "browser" extra and Chromium.'
            ) from exc
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=self._launch_args,
            )
        except Exception:
            await self._playwright.stop()
            self._playwright = None
            raise

    @classmethod
    def _url_allowed(cls, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or host in cls._BLOCKED_HOSTS or host.endswith(".local"):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )

    async def _route_guard(self, route, request) -> None:
        url = request.url
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and not self._url_allowed(url):
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    def _session(self, session_id: str) -> _PlaywrightSession:
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Unknown browser session: {session_id}")
        return session

    @staticmethod
    def _tab_id(session: _PlaywrightSession, page: Any) -> str:
        key = id(page)
        if key not in session.tab_ids:
            session.tab_ids[key] = uuid4().hex
        return session.tab_ids[key]

    async def create_session(self, session_id: str, *, viewport: dict[str, int]) -> BrowserState:
        if await self.has_session(session_id):
            return await self.view(session_id)
        self._sessions.pop(session_id, None)
        await self._ensure_runtime()
        context = await self._browser.new_context(
            viewport={"width": int(viewport["width"]), "height": int(viewport["height"])},
            accept_downloads=False,
        )
        await context.route("**/*", self._route_guard)
        page = await context.new_page()
        session = _PlaywrightSession(context=context, active_page=page, viewport=dict(viewport))
        self._sessions[session_id] = session
        self._tab_id(session, page)
        return await self._state(session_id, include_interactables=False)

    async def has_session(self, session_id: str) -> bool:
        return self._connected() and session_id in self._sessions

    async def _active(self, session_id: str):
        session = self._session(session_id)
        pages = [page for page in session.context.pages if not page.is_closed()]
        if not pages:
            session.active_page = await session.context.new_page()
            pages = [session.active_page]
        if session.active_page.is_closed() or session.active_page not in pages:
            session.active_page = pages[-1]
        for page in pages:
            self._tab_id(session, page)
        return session, session.active_page

    async def _state(self, session_id: str, *, include_interactables: bool) -> BrowserState:
        session, page = await self._active(session_id)
        tabs: list[BrowserTab] = []
        for index, candidate in enumerate([p for p in session.context.pages if not p.is_closed()]):
            try:
                title = await candidate.title()
            except Exception:
                title = ""
            tabs.append(
                BrowserTab(
                    id=self._tab_id(session, candidate),
                    index=index,
                    url=candidate.url,
                    title=title,
                    active=candidate is page,
                )
            )

        interactables: list[dict[str, Any]] = []
        sensitive_signals: list[str] = []
        text_excerpt = ""
        if include_interactables and page.url != "about:blank":
            try:
                snapshot = await page.evaluate(
                    """
                    () => {
                      const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                      };
                      const selectorFor = (el) => {
                        if (el.id) return '#' + CSS.escape(el.id);
                        const testId = el.getAttribute('data-testid');
                        if (testId) return `[data-testid="${CSS.escape(testId)}"]`;
                        const name = el.getAttribute('name');
                        if (name) return `${el.tagName.toLowerCase()}[name="${CSS.escape(name)}"]`;
                        const aria = el.getAttribute('aria-label');
                        if (aria) return `${el.tagName.toLowerCase()}[aria-label="${CSS.escape(aria)}"]`;
                        let node = el;
                        const parts = [];
                        while (node && node.nodeType === 1 && parts.length < 5) {
                          let part = node.tagName.toLowerCase();
                          const parent = node.parentElement;
                          if (parent) {
                            const peers = Array.from(parent.children).filter(x => x.tagName === node.tagName);
                            if (peers.length > 1) part += `:nth-of-type(${peers.indexOf(node) + 1})`;
                          }
                          parts.unshift(part);
                          node = parent;
                        }
                        return parts.join(' > ');
                      };
                      const candidates = Array.from(document.querySelectorAll(
                        'a,button,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]'
                      )).filter(visible).slice(0, 250);
                      const interactables = candidates.map((el) => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute('type') || '',
                        text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().slice(0, 220),
                        name: el.getAttribute('name') || '',
                        selector: selectorFor(el),
                        disabled: Boolean(el.disabled),
                      }));
                      const signals = [];
                      for (const el of candidates) {
                        const fingerprint = [
                          el.getAttribute('type'), el.getAttribute('autocomplete'), el.getAttribute('name'),
                          el.id, el.getAttribute('aria-label'), el.getAttribute('placeholder')
                        ].filter(Boolean).join(' ').toLowerCase();
                        if (el.getAttribute('type') === 'password' || /current-password|new-password/.test(fingerprint)) signals.push('login_credentials');
                        if (/one-time-code|otp|2fa|mfa|verification.?code|passcode/.test(fingerprint)) signals.push('otp_or_2fa');
                        if (/cc-number|cc-csc|cvv|cvc|card.?number|payment/.test(fingerprint)) signals.push('payment_or_card');
                      }
                      if (Array.from(document.querySelectorAll('iframe')).some(f => /recaptcha|hcaptcha|turnstile/i.test(f.src || ''))) signals.push('captcha');
                      const bodyText = (document.body?.innerText || '').slice(0, 100000);
                      return { interactables, sensitiveSignals: [...new Set(signals)], bodyText };
                    }
                    """
                )
                interactables = list(snapshot.get("interactables") or [])
                sensitive_signals = list(snapshot.get("sensitiveSignals") or [])
                if not sensitive_signals:
                    text_excerpt = str(snapshot.get("bodyText") or "")[:100_000]
            except Exception:
                pass

        try:
            title = await page.title()
        except Exception:
            title = ""
        return BrowserState(
            session_id=session_id,
            url=page.url,
            title=title,
            loading=session.loading,
            tabs=tabs,
            viewport=session.viewport,
            interactables=interactables,
            text_excerpt=text_excerpt,
            sensitive_signals=sensitive_signals,
        )

    async def navigate(self, session_id: str, url: str) -> BrowserState:
        if not self._url_allowed(url):
            raise ValueError("Navigation target is not allowed by the browser sandbox policy")
        session, page = await self._active(session_id)
        session.loading = True
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            session.active_page = page
        finally:
            session.loading = False
        return await self._state(session_id, include_interactables=False)

    async def view(self, session_id: str) -> BrowserState:
        return await self._state(session_id, include_interactables=True)

    async def click(self, session_id: str, selector: str) -> BrowserState:
        session, page = await self._active(session_id)
        locator = page.locator(selector)
        fingerprint = await locator.evaluate(
            """el => [
              el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title'),
              el.getAttribute('name'), el.id, el.getAttribute('value')
            ].filter(Boolean).join(' ').toLowerCase().slice(0, 1000)"""
        )
        if any(marker in str(fingerprint) for marker in self._SENSITIVE_CLICK_MARKERS):
            raise SensitiveBrowserOperation("Payment, banking, identity, or security confirmation requires user control")
        before = len(session.context.pages)
        await locator.click(timeout=15_000)
        pages = [p for p in session.context.pages if not p.is_closed()]
        if len(pages) > before:
            session.active_page = pages[-1]
        return await self._state(session_id, include_interactables=False)

    async def input(self, session_id: str, selector: str, value: str) -> BrowserState:
        _, page = await self._active(session_id)
        locator = page.locator(selector)
        info = await locator.evaluate(
            """el => ({
              type: (el.getAttribute('type') || '').toLowerCase(),
              autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(),
              name: (el.getAttribute('name') || '').toLowerCase(),
              id: (el.id || '').toLowerCase(),
              aria: (el.getAttribute('aria-label') || '').toLowerCase(),
              placeholder: (el.getAttribute('placeholder') || '').toLowerCase()
            })"""
        )
        fingerprint = " ".join(str(info.get(k, "")) for k in info)
        if info.get("type") == "password" or any(
            marker in fingerprint
            for marker in (
                "current-password", "new-password", "one-time-code", " otp", "2fa", "mfa",
                "verification code", "passcode", "cc-number", "cc-csc", "cvv", "cvc", "card number",
            )
        ):
            raise SensitiveBrowserOperation("This field contains credentials, OTP, payment, or security data")
        await locator.fill(value)
        return await self._state(session_id, include_interactables=False)

    async def press_key(self, session_id: str, key: str) -> BrowserState:
        _, page = await self._active(session_id)
        await page.keyboard.press(key)
        return await self._state(session_id, include_interactables=False)

    async def scroll(self, session_id: str, delta_x: float, delta_y: float) -> BrowserState:
        _, page = await self._active(session_id)
        await page.mouse.wheel(delta_x, delta_y)
        return await self._state(session_id, include_interactables=False)

    async def select_option(self, session_id: str, selector: str, value: str) -> BrowserState:
        _, page = await self._active(session_id)
        await page.locator(selector).select_option(value)
        return await self._state(session_id, include_interactables=False)

    async def back(self, session_id: str) -> BrowserState:
        _, page = await self._active(session_id)
        await page.go_back(wait_until="domcontentloaded", timeout=30_000)
        return await self._state(session_id, include_interactables=False)

    async def forward(self, session_id: str) -> BrowserState:
        _, page = await self._active(session_id)
        await page.go_forward(wait_until="domcontentloaded", timeout=30_000)
        return await self._state(session_id, include_interactables=False)

    async def refresh(self, session_id: str) -> BrowserState:
        _, page = await self._active(session_id)
        await page.reload(wait_until="domcontentloaded", timeout=30_000)
        return await self._state(session_id, include_interactables=False)

    async def get_tabs(self, session_id: str) -> BrowserState:
        return await self._state(session_id, include_interactables=False)

    async def switch_tab(self, session_id: str, tab_id: str) -> BrowserState:
        session = self._session(session_id)
        for page in [p for p in session.context.pages if not p.is_closed()]:
            if self._tab_id(session, page) == tab_id:
                session.active_page = page
                await page.bring_to_front()
                return await self._state(session_id, include_interactables=False)
        raise KeyError("Unknown browser tab")

    async def close_tab(self, session_id: str, tab_id: str) -> BrowserState:
        session = self._session(session_id)
        target = None
        for page in [p for p in session.context.pages if not p.is_closed()]:
            if self._tab_id(session, page) == tab_id:
                target = page
                break
        if not target:
            raise KeyError("Unknown browser tab")
        await target.close()
        pages = [p for p in session.context.pages if not p.is_closed()]
        session.active_page = pages[-1] if pages else await session.context.new_page()
        return await self._state(session_id, include_interactables=False)

    async def click_at(self, session_id: str, x: float, y: float) -> BrowserState:
        _, page = await self._active(session_id)
        await page.mouse.click(x, y)
        return await self._state(session_id, include_interactables=False)

    async def insert_text(self, session_id: str, text: str) -> BrowserState:
        _, page = await self._active(session_id)
        await page.keyboard.insert_text(text)
        return await self._state(session_id, include_interactables=False)

    async def capture_frame(self, session_id: str) -> BrowserFrame:
        session, page = await self._active(session_id)
        image = await page.screenshot(
            type="jpeg",
            quality=65,
            full_page=False,
            animations="disabled",
            caret="hide",
        )
        return BrowserFrame(
            data_base64=base64.b64encode(image).decode("ascii"),
            width=int(session.viewport["width"]),
            height=int(session.viewport["height"]),
        )

    async def cdp_snapshot(self, session_id: str) -> dict[str, Any]:
        """Optional Chromium diagnostics extension; callers stay behind the provider abstraction."""
        _, page = await self._active(session_id)
        cdp = await page.context.new_cdp_session(page)
        try:
            await cdp.send("Performance.enable")
            metrics = await cdp.send("Performance.getMetrics")
            history = await cdp.send("Page.getNavigationHistory")
            return {
                "metrics": metrics.get("metrics", []),
                "current_index": history.get("currentIndex"),
                "history_entries": history.get("entries", []),
            }
        finally:
            await cdp.detach()

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            try:
                await session.context.close()
            except Exception:
                pass

    async def close_all(self) -> None:
        for session_id in list(self._sessions):
            await self.close_session(session_id)
        await self._discard_runtime()

    async def probe(self) -> dict[str, Any]:
        await self._ensure_runtime()
        return {
            "ok": True,
            "engine": "chromium",
            "version": self._browser.version if self._browser else None,
            "cdp": True,
        }
