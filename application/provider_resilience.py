from __future__ import annotations

from dataclasses import dataclass

from domain.provider import ModelCallContext, ProviderError
from ports.audit import AuditPort
from ports.model_provider import ModelProviderPort


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    name: str
    provider: ModelProviderPort


class ResilientModelProvider:
    """Model-provider composite that preserves the same call context across failover.

    Each concrete adapter owns its own retries. This component only decides whether a
    retryable failure should advance to the next configured provider/model candidate.
    """

    def __init__(self, candidates: list[ProviderCandidate], audit: AuditPort | None = None):
        if not candidates:
            raise ValueError("At least one model provider candidate is required")
        self._candidates = list(candidates)
        self._audit = audit

    async def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        context: ModelCallContext | None = None,
    ) -> str:
        call_context = context or ModelCallContext()
        last_error: ProviderError | None = None
        for index, candidate in enumerate(self._candidates):
            try:
                result = await candidate.provider.complete(prompt, system=system, context=call_context)
                if self._audit and index > 0:
                    self._audit.record(
                        "provider.fallback_succeeded",
                        session_id=call_context.session_id,
                        data={"candidate": candidate.name, "purpose": call_context.purpose, "index": index},
                    )
                return result
            except ProviderError as exc:
                last_error = exc
                has_next = index + 1 < len(self._candidates)
                if self._audit:
                    self._audit.record(
                        "provider.candidate_failed",
                        session_id=call_context.session_id,
                        data={
                            "candidate": candidate.name,
                            "purpose": call_context.purpose,
                            "index": index,
                            "retryable": exc.retryable,
                            "status_code": exc.status_code,
                            "request_id": exc.request_id,
                            "will_fallback": bool(exc.retryable and has_next),
                        },
                    )
                if not exc.retryable or not has_next:
                    raise
        if last_error:
            raise last_error
        raise RuntimeError("Provider failover chain exited unexpectedly")
