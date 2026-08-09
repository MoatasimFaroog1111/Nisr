from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from super_agent.models import ToolResult, RiskLevel
from super_agent.tools.base import Tool
from super_agent.core.approvals import ApprovalManager


class BrowserSessionManager:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir=artifacts_dir; self.artifacts_dir.mkdir(parents=True,exist_ok=True)
        self.playwright=None; self.browser=None; self.page=None

    async def ensure(self):
        if self.page:return
        try: from playwright.async_api import async_playwright
        except ImportError as e: raise RuntimeError('Browser automation requires: pip install -e ".[browser]" then playwright install chromium') from e
        self.playwright=await async_playwright().start(); self.browser=await self.playwright.chromium.launch(headless=True); self.page=await self.browser.new_page()

    async def close(self):
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()
        self.playwright=self.browser=self.page=None


class BrowserTool(Tool):
    name="browser"; description="Browser automation. args: operation(open|snapshot|click|fill|screenshot|close), plus url/selector/value as required. Interactive actions require approval."
    def __init__(self,sessions:BrowserSessionManager,approvals:ApprovalManager):self.sessions=sessions; self.approvals=approvals
    async def run(self,arguments:dict[str,Any])->ToolResult:
        op=str(arguments.get("operation","")).lower(); token=str(arguments.get("approval_token",""))
        try:
            if op=="close": await self.sessions.close(); return ToolResult(ok=True,output="Browser closed")
            await self.sessions.ensure(); page=self.sessions.page
            if op=="open":
                url=str(arguments.get("url",""));
                if urlparse(url).scheme not in {"http","https"}:return ToolResult(ok=False,error="Only HTTP(S) navigation is allowed")
                resp=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
                return ToolResult(ok=True,output={"url":page.url,"title":await page.title(),"status":resp.status if resp else None})
            if op=="snapshot":
                text=(await page.locator("body").inner_text())[:100000]
                return ToolResult(ok=True,output={"url":page.url,"title":await page.title(),"text":text})
            if op=="screenshot":
                name=Path(str(arguments.get("name","browser.png"))).name; path=self.sessions.artifacts_dir/name
                await page.screenshot(path=str(path),full_page=bool(arguments.get("full_page",True)))
                return ToolResult(ok=True,output=str(path),metadata={"changed_artifact":str(path)})
            if op in {"click","fill"}:
                payload={"operation":op,"url":page.url,"selector":str(arguments.get("selector","")),"value":str(arguments.get("value","")) if op=="fill" else ""}
                ok,req=self.approvals.authorize_or_request("browser_interaction",payload,RiskLevel.MEDIUM,token)
                if not ok:return ToolResult(ok=False,error="Browser interaction requires authorization",metadata={"approval_required":req,"risk":"medium"})
                selector=payload["selector"]
                if not selector:return ToolResult(ok=False,error="selector is required")
                if op=="click":await page.locator(selector).click()
                else:await page.locator(selector).fill(payload["value"])
                return ToolResult(ok=True,output={"url":page.url,"operation":op})
            return ToolResult(ok=False,error="Unknown browser operation")
        except Exception as e:return ToolResult(ok=False,error=str(e))
