from __future__ import annotations

import re
from pathlib import Path

from domain.models import RiskLevel


ACTION_PROTOCOL = """
Return exactly one JSON object matching one form:
Tool: {"action":"tool","thought_summary":"short reason","tool":{"name":"tool_name","arguments":{}}}
Delegate: {"action":"delegate","subagent_role":"researcher","subagent_task":"..."}
Parallel delegates: {"action":"delegate_parallel","subagents":[{"role":"researcher","task":"..."},{"role":"tester","task":"..."}]}
Memory: {"action":"memory_write","memory_key":"...","memory_value":"..."}
Plan update: {"action":"plan_update","plan":{"tasks":[...]}}
Finish: {"action":"finish","result":"final user-facing result"}
Do not wrap JSON in markdown.
"""


SYSTEM_PROMPT = """
You are Nisr, a production autonomous agent operating through a controlled tool runtime.

MISSION
Resolve the user's objective end-to-end. Do not guess when evidence can be gathered.

OPERATING LOOP
1. Understand the objective, constraints, environment, and desired deliverable.
2. Research missing facts using available tools.
3. For non-trivial work, maintain a concrete plan with verifiable tasks.
4. Execute the smallest reliable action that advances the objective.
5. Verify substantive changes with diagnostics/tests/logs/runtime evidence when available.
6. If verification fails, diagnose root cause, repair, and verify again.
7. Use memory for durable facts and retrieve relevant memory when helpful.
8. Delegate independent specialist work when that increases quality or speed.
9. Do not declare success until the objective is actually satisfied or a real blocker remains.

ARCHITECTURAL RULES
- Domain and application behavior are vendor-agnostic.
- External systems are accessed only through registered ports/adapters.
- Prefer evidence over assumptions and never invent tool results.
- Shared files, schemas, public APIs, and state mutations must be serialized.
- Destructive or sensitive actions require authorization through the runtime.

COMMUNICATION
Return concise results and evidence. Do not expose private chain-of-thought.
Use the JSON action protocol exactly.
"""


class RiskPolicy:
    """Pure domain service for classifying operational risk."""

    BLOCKED_PATTERNS = [
        r"\brm\s+-rf\s+/(?:\s|$)",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r":\(\)\s*\{\s*:\|:&\s*\};:",
        r"\bshutdown\b",
        r"\breboot\b",
    ]
    HIGH_RISK_PATTERNS = [
        r"\brm\b",
        r"\bdel\b",
        r"\brmdir\b",
        r"\bdrop\s+(database|table)\b",
        r"\btruncate\s+table\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\s+-[a-z]*f",
        r"\bcurl\b.*\|\s*(sh|bash)\b",
        r"\bchmod\s+-r\b",
    ]
    MEDIUM_RISK_PATTERNS = [
        r"\bpip\s+install\b",
        r"\bnpm\s+install\b",
        r"\bapt(-get)?\s+install\b",
        r"\bgit\s+push\b",
        r"\bgit\s+(commit|checkout|switch|merge|rebase)\b",
        r"\bdocker\s+(run|build|push|stop|rm)\b",
    ]

    def classify_command(self, command: str) -> RiskLevel:
        lowered = command.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, lowered):
                return RiskLevel.BLOCKED
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, lowered):
                return RiskLevel.HIGH
        for pattern in self.MEDIUM_RISK_PATTERNS:
            if re.search(pattern, lowered):
                return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def classify_write(self, path: Path, workspace: Path) -> RiskLevel:
        try:
            path.resolve().relative_to(workspace.resolve())
            return RiskLevel.MEDIUM
        except ValueError:
            return RiskLevel.HIGH

    def classify_sql(self, sql: str) -> RiskLevel:
        stripped = re.sub(
            r"--.*?$|/\*.*?\*/", "", sql, flags=re.MULTILINE | re.DOTALL
        ).strip().lower()
        if re.match(
            r"^(select|with\b.*select|pragma\s+(table_info|index_list|database_list))\b",
            stripped,
            re.DOTALL,
        ):
            return RiskLevel.LOW
        if re.search(r"\b(drop\s+(database|table)|truncate\s+table)\b", stripped):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
