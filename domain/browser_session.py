from __future__ import annotations

from time import time
from typing import Any

from pydantic import BaseModel, Field

from domain.browser import BrowserControlOwner, BrowserControlState, BrowserTab


class BrowserSessionSnapshot(BaseModel):
    """Serializable browser-session state; never contains Playwright runtime objects or form values."""

    version: int = 1
    session_id: str
    user_id: str
    task_id: str | None = None
    owner: BrowserControlOwner = BrowserControlOwner.AGENT
    control_state: BrowserControlState = BrowserControlState.AGENT_CONTROL
    browser_started: bool = False
    takeover_requested: bool = False
    takeover_reason: str | None = None
    current_url: str = "about:blank"
    tabs: list[BrowserTab] = Field(default_factory=list)
    storage_state: dict[str, Any] = Field(default_factory=dict)
    updated_at_epoch: float = Field(default_factory=time)
    expires_at_epoch: float
    exact_history_restored: bool = False
    session_storage_restored: bool = False
