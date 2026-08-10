from __future__ import annotations

from domain.models import AgentState
from domain.state_invariants import AgentStateInvariantPolicy
from ports.session import SessionStorePort


class GuardedSessionStore:
    """Session-store decorator that enforces domain invariants at the persistence boundary."""

    def __init__(self, inner: SessionStorePort, policy: AgentStateInvariantPolicy | None = None):
        self._inner = inner
        self._policy = policy or AgentStateInvariantPolicy()

    def save(self, state: AgentState, status: str) -> None:
        self._policy.assert_valid(state)
        self._inner.save(state, status)

    def load(self, session_id: str) -> AgentState | None:
        state = self._inner.load(session_id)
        if state is not None:
            self._policy.assert_valid(state)
        return state

    def find_session_by_approval(self, request_id: str) -> str | None:
        return self._inner.find_session_by_approval(request_id)
