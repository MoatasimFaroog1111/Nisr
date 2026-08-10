from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCallContext:
    """Vendor-neutral metadata for one model call; never contains prompt or secrets."""

    session_id: str = ""
    purpose: str = "agent"


@dataclass(frozen=True, slots=True)
class ProviderCallMetrics:
    """Sanitized provider metrics with no raw prompt, response, or credentials."""

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


class ProviderError(RuntimeError):
    """Vendor-neutral model-provider failure surfaced beyond an adapter boundary."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id


class ProviderUnavailableError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass
