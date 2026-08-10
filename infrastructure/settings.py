from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


_INSECURE_SECRET_PLACEHOLDERS = {
    "",
    "change-me-in-production",
    "replace-with-a-long-random-secret",
    "replace-with-a-different-long-random-secret",
}


def _browser_session_secret() -> str:
    explicit = os.getenv("AGENT_BROWSER_SESSION_SECRET", "").strip()
    if explicit not in _INSECURE_SECRET_PLACEHOLDERS:
        return explicit
    approval = os.getenv("AGENT_APPROVAL_SECRET", "").strip()
    if approval not in _INSECURE_SECRET_PLACEHOLDERS:
        return approval
    return secrets.token_urlsafe(48)


class Settings(BaseModel):
    provider: str = os.getenv("AGENT_PROVIDER", "openai_compatible")
    model: str = os.getenv("AGENT_MODEL", "")
    api_base: str = os.getenv("AGENT_API_BASE", "https://api.openai.com/v1")
    api_key: str = os.getenv("AGENT_API_KEY", "")
    provider_max_retries: int = int(os.getenv("AGENT_PROVIDER_MAX_RETRIES", "2"))
    provider_retry_base_seconds: float = float(os.getenv("AGENT_PROVIDER_RETRY_BASE_SECONDS", "0.8"))
    fallback_provider: str = os.getenv("AGENT_FALLBACK_PROVIDER", "").strip()
    fallback_model: str = os.getenv("AGENT_FALLBACK_MODEL", "").strip()
    fallback_api_base: str = os.getenv("AGENT_FALLBACK_API_BASE", os.getenv("AGENT_API_BASE", "https://api.openai.com/v1"))
    fallback_api_key: str = os.getenv("AGENT_FALLBACK_API_KEY", os.getenv("AGENT_API_KEY", ""))
    run_token_budget: int = int(os.getenv("AGENT_RUN_TOKEN_BUDGET", "24000"))
    provider_token_reserve: int = int(os.getenv("AGENT_PROVIDER_TOKEN_RESERVE", "4000"))
    token_chars_per_token: float = float(os.getenv("AGENT_TOKEN_CHARS_PER_TOKEN", "4.0"))
    min_context_budget_chars: int = int(os.getenv("AGENT_MIN_CONTEXT_BUDGET_CHARS", "8000"))
    context_budget_safety_ratio: float = float(os.getenv("AGENT_CONTEXT_BUDGET_SAFETY_RATIO", "0.65"))
    workspace: Path = Path(os.getenv("AGENT_WORKSPACE", "./workspace")).resolve()
    memory_db: Path = Path(os.getenv("AGENT_MEMORY_DB", "./data/agent_memory.sqlite3")).resolve()
    approval_db: Path = Path(os.getenv("AGENT_APPROVAL_DB", "./data/approvals.sqlite3")).resolve()
    session_db: Path = Path(os.getenv("AGENT_SESSION_DB", "./data/sessions.sqlite3")).resolve()
    approval_secret: str = os.getenv("AGENT_APPROVAL_SECRET", "change-me-in-production")
    browser_session_secret: str = _browser_session_secret()
    browser_token_ttl_seconds: int = int(os.getenv("AGENT_BROWSER_TOKEN_TTL_SECONDS", "3600"))
    browser_session_timeout_seconds: int = int(os.getenv("AGENT_BROWSER_SESSION_TIMEOUT_SECONDS", "1200"))
    browser_cleanup_interval_seconds: int = int(os.getenv("AGENT_BROWSER_CLEANUP_INTERVAL_SECONDS", "30"))
    browser_frame_interval_ms: int = int(os.getenv("AGENT_BROWSER_FRAME_INTERVAL_MS", "650"))
    browser_viewport_width: int = int(os.getenv("AGENT_BROWSER_VIEWPORT_WIDTH", "1280"))
    browser_viewport_height: int = int(os.getenv("AGENT_BROWSER_VIEWPORT_HEIGHT", "720"))
    browser_max_sessions: int = int(os.getenv("AGENT_BROWSER_MAX_SESSIONS", "8"))
    audit_log: Path = Path(os.getenv("AGENT_AUDIT_LOG", "./data/audit.jsonl")).resolve()
    artifacts_dir: Path = Path(os.getenv("AGENT_ARTIFACTS_DIR", "./artifacts")).resolve()
    database_url: str = os.getenv("AGENT_DATABASE_URL", "")
    github_token: str = os.getenv("AGENT_GITHUB_TOKEN", "")
    github_api_base: str = os.getenv("AGENT_GITHUB_API_BASE", "https://api.github.com")
    web_user_agent: str = os.getenv("AGENT_WEB_USER_AGENT", "Nisr/0.4.5")
    max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "30"))
    context_budget_chars: int = int(os.getenv("AGENT_CONTEXT_BUDGET_CHARS", "50000"))
    auto_approve_low_risk: bool = os.getenv("AGENT_AUTO_APPROVE_LOW_RISK", "true").lower() == "true"

    def prepare_directories(self) -> None:
        for path in (
            self.workspace,
            self.memory_db.parent,
            self.approval_db.parent,
            self.session_db.parent,
            self.audit_log.parent,
            self.artifacts_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.prepare_directories()
