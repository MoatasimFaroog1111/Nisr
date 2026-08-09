from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from adapters.tools.base import BaseTool
from domain.models import RiskLevel, ToolResult
from ports.approval import ApprovalPort


class BrowserSession:
    def __init__(self, artifacts_dir: Path):
        self._artifacts_dir = artifacts_dir
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._browser = None
        self.page = None

    async def ensure(self) -> None:
        if self.page:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Browser automation is not installed in this runtime. Install the "browser" extra and Chromium.'
            ) from exc
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage"],
            )
            self.page = await self._browser.new_page()
        except Exception:
            await self._playwright.stop()
            self._playwright = None
            raise

    async def probe(self) -> dict[str, Any]:
        await self.ensure()
        return {
            "ok": True,
            "engine": "chromium",
            "version": self._browser.version if self._browser else None,
        }

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._playwright = self._browser = self.page = None

    def screenshot_path(self, name: str) -> Path:
        return self._artifacts_dir / Path(name).name


class PlaywrightBrowserTool(BaseTool):
    name = "browser"
    description = "Browser automation. args: operation(open|snapshot|click|fill|screenshot|close), plus url/selector/value as required. For resumable click/fill, url may be supplied so the browser restores that page before the action. Interactive actions require approval."

    def __init__(self, session: BrowserSession, approvals: ApprovalPort):
        self._session = session
        self._approvals = approvals

    @staticmethod
    def _valid_http_url(url: str) -> bool:
        return urlparse(url).scheme in {"http", "https"}

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "")).lower()
        try:
            if operation == "close":
                await self._session.close()
                return ToolResult(ok=True, output="Browser closed")
            await self._session.ensure()
            page = self._session.page
            if operation == "open":
                url = str(arguments.get("url", ""))
                if not self._valid_http_url(url):
                    return ToolResult(ok=False, error="Only HTTP(S) navigation is allowed")
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                return ToolResult(
                    ok=True,
                    output={
                        "url": page.url,
                        "title": await page.title(),
                        "status": response.status if response else None,
                    },
                )
            if operation == "snapshot":
                text = (await page.locator("body").inner_text())[:100_000]
                return ToolResult(
                    ok=True,
                    output={"url": page.url, "title": await page.title(), "text": text},
                )
            if operation == "screenshot":
                path = self._session.screenshot_path(str(arguments.get("name", "browser.png")))
                await page.screenshot(path=str(path), full_page=bool(arguments.get("full_page", True)))
                return ToolResult(
                    ok=True,
                    output=str(path),
                    metadata={"changed_artifact": str(path)},
                )
            if operation in {"click", "fill"}:
                restore_url = str(arguments.get("url", "")).strip()
                if restore_url:
                    if not self._valid_http_url(restore_url):
                        return ToolResult(ok=False, error="Only HTTP(S) navigation is allowed")
                    if page.url != restore_url:
                        await page.goto(restore_url, wait_until="domcontentloaded", timeout=30_000)
                payload = {
                    "operation": operation,
                    "url": page.url,
                    "selector": str(arguments.get("selector", "")),
                    "value": str(arguments.get("value", "")) if operation == "fill" else "",
                }
                allowed, request = self._approvals.authorize_or_request(
                    "browser_interaction",
                    payload,
                    RiskLevel.MEDIUM,
                    str(arguments.get("approval_token", "")),
                )
                if not allowed:
                    approval = dict(request or {})
                    approval["action_payload"] = payload
                    return ToolResult(
                        ok=False,
                        error="Browser interaction requires authorization",
                        metadata={"approval_required": approval, "risk": "medium"},
                    )
                if not payload["selector"]:
                    return ToolResult(ok=False, error="selector is required")
                if operation == "click":
                    await page.locator(payload["selector"]).click()
                else:
                    await page.locator(payload["selector"]).fill(payload["value"])
                return ToolResult(ok=True, output={"url": page.url, "operation": operation})
            return ToolResult(ok=False, error="Unknown browser operation")
        except Exception as exc:
            return ToolResult(
                ok=False,
                error=f"Browser operation failed: {exc}",
                metadata={"error_type": type(exc).__name__, "operation": operation},
            )
