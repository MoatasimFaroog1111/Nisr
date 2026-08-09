from __future__ import annotations

from typing import Protocol

from domain.models import AgentState


class SessionStorePort(Protocol):
    def save(self, state: AgentState, status: str) -> None: ...
    def load(self, session_id: str) -> AgentState | None: ...
    def find_session_by_approval(self, request_id: str) -> str | None: ...
