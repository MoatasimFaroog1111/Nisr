from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ports.model_provider import ModelCallContext


@dataclass(frozen=True, slots=True)
class ProviderCallMetrics:
    """Sanitized provider metrics. Raw prompts, responses and credentials are intentionally absent."""

    context: ModelCallContext
    status_code: int | None
    request_id: str | None = None
    attempt: int = 1
    retrying: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests: str | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens: str | None = None
    error_type: str | None = None


class ProviderTelemetryPort(Protocol):
    def record(self, metrics: ProviderCallMetrics) -> None: ...
