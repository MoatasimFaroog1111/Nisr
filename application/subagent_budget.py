from __future__ import annotations

from application.execution import SubagentCoordinator
from domain.models import SubagentRequest
from ports.model_provider import ModelProviderPort
from ports.token_budget import TokenBudgetPort


class AdaptiveSubagentCoordinator(SubagentCoordinator):
    """Reduces parallel model calls as run/provider token headroom shrinks."""

    def __init__(
        self,
        provider: ModelProviderPort,
        token_budget: TokenBudgetPort,
        max_parallel: int = 6,
    ):
        super().__init__(provider, max_parallel=max_parallel)
        self._token_budget = token_budget
        self._max_parallel = max(1, int(max_parallel))

    async def run_many(
        self,
        requests: list[SubagentRequest],
        context: str,
        *,
        session_id: str = "",
    ) -> list[dict[str, str]]:
        reports: list[dict[str, str]] = []
        cursor = 0
        while cursor < len(requests):
            remaining = len(requests) - cursor
            requested = min(self._max_parallel, remaining)
            parallelism = self._token_budget.recommended_parallelism(session_id, requested)
            chunk = requests[cursor : cursor + parallelism]
            reports.extend(
                await super().run_many(chunk, context, session_id=session_id)
            )
            cursor += len(chunk)
        return reports
