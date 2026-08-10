from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BrowserControlOwner(str, Enum):
    AGENT = "agent"
    USER = "user"


class BrowserControlState(str, Enum):
    AGENT_CONTROL = "AGENT_CONTROL"
    USER_CONTROL = "USER_CONTROL"
    TRANSITIONING = "TRANSITIONING"


class BrowserTab(BaseModel):
    id: str
    index: int
    url: str = "about:blank"
    title: str = ""
    active: bool = False


class BrowserState(BaseModel):
    session_id: str
    task_id: str | None = None
    owner: BrowserControlOwner = BrowserControlOwner.AGENT
    control_state: BrowserControlState = BrowserControlState.AGENT_CONTROL
    url: str = "about:blank"
    title: str = ""
    loading: bool = False
    tabs: list[BrowserTab] = Field(default_factory=list)
    viewport: dict[str, int] = Field(default_factory=dict)
    interactables: list[dict[str, Any]] = Field(default_factory=list)
    text_excerpt: str = ""
    sensitive_signals: list[str] = Field(default_factory=list)
    reliability: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BrowserEvent(BaseModel):
    type: str
    session_id: str
    task_id: str | None = None
    actor: str | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BrowserFrame(BaseModel):
    mime_type: str = "image/jpeg"
    data_base64: str
    width: int
    height: int
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BrowserControlError(RuntimeError):
    """Raised when an actor attempts a browser action without owning control."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SensitiveBrowserOperation(RuntimeError):
    """Raised when a browser action must be handed to the user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
