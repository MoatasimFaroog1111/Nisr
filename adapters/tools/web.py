from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from adapters.tools.base import BaseTool
from domain.models import ToolResult


class _DuckDuckGoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_result = False
        self._href = ""
        self._buffer: list[str] = []
        self.results: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and "result__a" in attributes.get("class", ""):
            self._in_result = True
            self._href = attributes.get("href", "")
            self._buffer = []

    def handle_data(self, data):
        if self._in_result:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result:
            title = "".join(self._buffer).strip()
            if title:
                self.results.append({"title": title, "url": self._href})
            self._in_result = False


def _is_http_url(url: str) -> bool:
    try:
        return urlparse(url).scheme in {"http", "https"}
    except Exception:
        return False


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the public web. args: query, optional limit. Returns titles and URLs."

    def __init__(self, user_agent: str = "Nisr/0.3"):
        self._user_agent = user_agent

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        limit = max(1, min(int(arguments.get("limit", 8)), 20))
        if not query:
            return ToolResult(ok=False, error="query is required")
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": self._user_agent},
            ) as client:
                response = await client.get(url)
            response.raise_for_status()
            parser = _DuckDuckGoParser()
            parser.feed(response.text)
            return ToolResult(
                ok=True,
                output=parser.results[:limit],
                metadata={"query": query, "engine": "duckduckgo-html"},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch a public HTTP(S) URL as text. args: url, optional max_chars."

    def __init__(self, user_agent: str = "Nisr/0.3"):
        self._user_agent = user_agent

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        url = str(arguments.get("url", "")).strip()
        if not _is_http_url(url):
            return ToolResult(ok=False, error="Only HTTP(S) URLs are allowed")
        max_chars = min(int(arguments.get("max_chars", 120_000)), 500_000)
        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": self._user_agent},
            ) as client:
                response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not any(
                marker in content_type
                for marker in ("text/", "json", "xml", "javascript", "html")
            ):
                return ToolResult(
                    ok=False, error=f"Unsupported content-type: {content_type}"
                )
            return ToolResult(
                ok=True,
                output=response.text[:max_chars],
                metadata={
                    "url": str(response.url),
                    "status": response.status_code,
                    "content_type": content_type,
                },
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
