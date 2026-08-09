from __future__ import annotations

from typing import Any

import httpx

from adapters.tools.base import BaseTool
from domain.models import RiskLevel, ToolResult
from ports.approval import ApprovalPort


class GitHubRestTool(BaseTool):
    name = "github"
    description = "GitHub REST operations. args: operation(repo|get_issues|get_prs|create_issue|comment_issue), owner, repo and relevant fields. Writes require approval."

    def __init__(self, token: str, api_base: str, approvals: ApprovalPort):
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._approvals = approvals

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Nisr/0.3"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "repo"))
        owner = str(arguments.get("owner", ""))
        repo = str(arguments.get("repo", ""))
        if not owner or not repo:
            return ToolResult(ok=False, error="owner and repo are required")
        path = f"/repos/{owner}/{repo}"
        method = "GET"
        body = None
        if operation == "repo":
            pass
        elif operation == "get_issues":
            path += "/issues"
        elif operation == "get_prs":
            path += "/pulls"
        elif operation == "create_issue":
            method = "POST"
            path += "/issues"
            body = {"title": str(arguments.get("title", "")), "body": str(arguments.get("body", ""))}
        elif operation == "comment_issue":
            method = "POST"
            path += f"/issues/{int(arguments['number'])}/comments"
            body = {"body": str(arguments.get("body", ""))}
        else:
            return ToolResult(ok=False, error="Unknown GitHub operation")

        if method != "GET":
            payload = {"operation": operation, "owner": owner, "repo": repo, "body": body}
            allowed, request = self._approvals.authorize_or_request(
                "github_write",
                payload,
                RiskLevel.MEDIUM,
                str(arguments.get("approval_token", "")),
            )
            if not allowed:
                return ToolResult(
                    ok=False,
                    error="GitHub write requires authorization",
                    metadata={"approval_required": request, "risk": "medium"},
                )
            if not self._token:
                return ToolResult(ok=False, error="AGENT_GITHUB_TOKEN is required for GitHub writes")
        try:
            async with httpx.AsyncClient(timeout=30, headers=self._headers()) as client:
                response = await client.request(method, self._api_base + path, json=body)
            if response.status_code >= 400:
                return ToolResult(
                    ok=False,
                    error=f"GitHub HTTP {response.status_code}: {response.text[:2000]}",
                )
            return ToolResult(
                ok=True,
                output=response.json(),
                metadata={"status": response.status_code, "operation": operation},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
