from __future__ import annotations

from typing import Any

from domain.contracts import RiskPolicy
from domain.models import RiskLevel, ToolResult
from ports.approval import ApprovalPort
from ports.database import DatabasePort


class DatabaseTool:
    name = "database"
    description = (
        "Database access. args: operation(query|execute), sql, optional params, "
        "optional approval_token. Adapter selection is done by composition root."
    )

    def __init__(self, database: DatabasePort, risk: RiskPolicy, approvals: ApprovalPort):
        self._database = database
        self._risk = risk
        self._approvals = approvals

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "query"))
        sql = str(arguments.get("sql", "")).strip()
        params = list(arguments.get("params", []))
        token = str(arguments.get("approval_token", ""))
        if not sql:
            return ToolResult(ok=False, error="sql is required")
        risk = self._risk.classify_sql(sql)
        if operation == "query":
            if risk != RiskLevel.LOW:
                return ToolResult(
                    ok=False,
                    error=f"query operation accepts read-only SQL; classified {risk.value}",
                )
            try:
                return ToolResult(
                    ok=True,
                    output=await self._database.query(sql, params),
                    metadata={"risk": risk.value, "operation": operation},
                )
            except Exception as exc:
                return ToolResult(ok=False, error=str(exc))
        if operation != "execute":
            return ToolResult(ok=False, error="Unknown database operation")
        payload = {"sql": sql, "params": params}
        allowed, request = self._approvals.authorize_or_request(
            "database_execute", payload, risk, token
        )
        if not allowed:
            return ToolResult(
                ok=False,
                error=f"Database execute requires authorization ({risk.value})",
                metadata={"approval_required": request, "risk": risk.value},
            )
        try:
            return ToolResult(
                ok=True,
                output=await self._database.execute(sql, params),
                metadata={"risk": risk.value, "operation": operation},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
