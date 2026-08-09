from __future__ import annotations

import re
from pathlib import Path
from super_agent.models import RiskLevel


class RiskGate:
    BLOCKED_PATTERNS = [
        r"\brm\s+-rf\s+/(?:\s|$)", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\s*\{\s*:\|:&\s*\};:",
        r"\bshutdown\b", r"\breboot\b",
    ]
    HIGH_RISK_PATTERNS = [
        r"\brm\b", r"\bdel\b", r"\brmdir\b", r"\bdrop\s+(database|table)\b", r"\btruncate\s+table\b",
        r"\bgit\s+reset\s+--hard\b", r"\bgit\s+clean\s+-[a-z]*f", r"\bcurl\b.*\|\s*(sh|bash)\b", r"\bchmod\s+-r\b",
    ]
    MEDIUM_RISK_PATTERNS = [
        r"\bpip\s+install\b", r"\bnpm\s+install\b", r"\bapt(-get)?\s+install\b", r"\bgit\s+push\b",
        r"\bgit\s+(commit|checkout|switch|merge|rebase)\b", r"\bdocker\s+(run|build|push|stop|rm)\b",
    ]

    def classify_command(self, command: str) -> RiskLevel:
        lowered = command.lower()
        for pat in self.BLOCKED_PATTERNS:
            if re.search(pat, lowered): return RiskLevel.BLOCKED
        for pat in self.HIGH_RISK_PATTERNS:
            if re.search(pat, lowered): return RiskLevel.HIGH
        for pat in self.MEDIUM_RISK_PATTERNS:
            if re.search(pat, lowered): return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def classify_write(self, path: Path, workspace: Path) -> RiskLevel:
        try:
            path.resolve().relative_to(workspace.resolve())
            return RiskLevel.MEDIUM
        except ValueError:
            return RiskLevel.HIGH

    def classify_sql(self, sql: str) -> RiskLevel:
        stripped = re.sub(r"--.*?$|/\*.*?\*/", "", sql, flags=re.MULTILINE | re.DOTALL).strip().lower()
        if re.match(r"^(select|with\b.*select|pragma\s+(table_info|index_list|database_list))\b", stripped, re.DOTALL):
            return RiskLevel.LOW
        if re.search(r"\b(drop\s+(database|table)|truncate\s+table)\b", stripped):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    def is_authorized(self, risk: RiskLevel, approvals: list[str], token: str) -> bool:
        if risk == RiskLevel.LOW: return True
        if risk == RiskLevel.BLOCKED: return False
        return token in approvals or f"risk:{risk.value}" in approvals
