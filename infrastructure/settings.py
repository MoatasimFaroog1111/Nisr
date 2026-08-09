from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    provider: str = os.getenv("AGENT_PROVIDER", "openai_compatible")
    model: str = os.getenv("AGENT_MODEL", "")
    api_base: str = os.getenv("AGENT_API_BASE", "https://api.openai.com/v1")
    api_key: str = os.getenv("AGENT_API_KEY", "")
    workspace: Path = Path(os.getenv("AGENT_WORKSPACE", "./workspace")).resolve()
    memory_db: Path = Path(os.getenv("AGENT_MEMORY_DB", "./data/agent_memory.sqlite3")).resolve()
    approval_db: Path = Path(os.getenv("AGENT_APPROVAL_DB", "./data/approvals.sqlite3")).resolve()
    approval_secret: str = os.getenv("AGENT_APPROVAL_SECRET", "change-me-in-production")
    audit_log: Path = Path(os.getenv("AGENT_AUDIT_LOG", "./data/audit.jsonl")).resolve()
    artifacts_dir: Path = Path(os.getenv("AGENT_ARTIFACTS_DIR", "./artifacts")).resolve()
    database_url: str = os.getenv("AGENT_DATABASE_URL", "")
    github_token: str = os.getenv("AGENT_GITHUB_TOKEN", "")
    github_api_base: str = os.getenv("AGENT_GITHUB_API_BASE", "https://api.github.com")
    web_user_agent: str = os.getenv("AGENT_WEB_USER_AGENT", "Nisr/0.3")
    max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "30"))
    context_budget_chars: int = int(os.getenv("AGENT_CONTEXT_BUDGET_CHARS", "50000"))
    auto_approve_low_risk: bool = os.getenv("AGENT_AUTO_APPROVE_LOW_RISK", "true").lower() == "true"

    def prepare_directories(self) -> None:
        for path in (self.workspace, self.memory_db.parent, self.approval_db.parent, self.audit_log.parent, self.artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.prepare_directories()
