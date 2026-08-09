from __future__ import annotations

from domain.models import AgentState


def public_agent_state(state: AgentState) -> dict:
    """Serialize state for clients without exposing ownership or authorization secrets."""
    return state.model_dump(mode="json", exclude={"user_id", "user_approvals"})
