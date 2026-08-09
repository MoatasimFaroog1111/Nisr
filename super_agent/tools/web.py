from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlparse
import httpx
from super_agent.models import ToolResult
from super_agent.tools.base import Tool


class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_result=False; self.href=""; self.buf=[]; self.results=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="a" and "result__a" in attrs.get("class",""):
            self.in_result=True; self.href=attrs.get("href",""); self.buf=[]
    def handle_data(self,data):
        if self.in_result:self.buf.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.in_result:
            title="".join(self.buf).strip()
            if title:self.results.append({"title":title,"url":self.href})
            self.in_result=False


def _http_url(url:str)->bool:
    try:return urlparse(url).scheme in {"http","https"}
    except Exception:return False


class WebSearchTool(Tool):
    name="web_search"; description="Search the public web. args: query, optional limit. Returns titles and URLs."
    def __init__(self,user_agent:str="SuperAgent/0.2"):self.user_agent=user_agent
    async def run(self,arguments:dict[str,Any])->ToolResult:
        query=str(arguments.get("query","")).strip(); limit=max(1,min(int(arguments.get("limit",8)),20))
        if not query:return ToolResult(ok=False,error="query is required")
        try:
            url=f"https://html.duckduckgo.com/html/?q={quote(query)}"
            async with httpx.AsyncClient(timeout=20,follow_redirects=True,headers={"User-Agent":self.user_agent}) as client:r=await client.get(url)
            r.raise_for_status(); parser=_DDGParser(); parser.feed(r.text)
            return ToolResult(ok=True,output=parser.results[:limit],metadata={"query":query,"engine":"duckduckgo-html"})
        except Exception as e:return ToolResult(ok=False,error=str(e))


class WebFetchTool(Tool):
    name="web_fetch"; description="Fetch a public HTTP(S) URL as text. args: url, optional max_chars."
    def __init__(self,user_agent:str="SuperAgent/0.2"):self.user_agent=user_agent
    async def run(self,arguments:dict[str,Any])->ToolResult:
        url=str(arguments.get("url","")).strip(); max_chars=min(int(arguments.get("max_chars",120000)),500000)
        if not _http_url(url):return ToolResult(ok=False,error="Only HTTP(S) URLs are allowed")
        try:
            async with httpx.AsyncClient(timeout=30,follow_redirects=True,headers={"User-Agent":self.user_agent}) as client:r=await client.get(url)
            r.raise_for_status(); ctype=r.headers.get("content-type","")
            if not any(x in ctype for x in ("text/","json","xml","javascript","html")):
                return ToolResult(ok=False,error=f"Unsupported content-type: {ctype}")
            return ToolResult(ok=True,output=r.text[:max_chars],metadata={"url":str(r.url),"status":r.status_code,"content_type":ctype})
        except Exception as e:return ToolResult(ok=False,error=str(e))
