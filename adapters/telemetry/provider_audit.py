from __future__ import annotations

from ports.audit import AuditPort
from ports.provider_telemetry import ProviderCallMetrics


class AuditProviderTelemetry:
    """Writes sanitized provider diagnostics to the existing audit stream."""

    def __init__(self, audit: AuditPort):
        self._audit = audit

    def record(self, metrics: ProviderCallMetrics) -> None:
        self._audit.record(
            "provider.telemetry",
            session_id=metrics.context.session_id,
            data={
                "purpose": metrics.context.purpose,
                "status": metrics.status_code,
                "request_id": metrics.request_id,
                "attempt": metrics.attempt,
                "retrying": metrics.retrying,
                "usage": {
                    "prompt_tokens": metrics.prompt_tokens,
                    "completion_tokens": metrics.completion_tokens,
                    "total_tokens": metrics.total_tokens,
                },
                "rate_limits": {
                    "limit_requests": metrics.limit_requests,
                    "remaining_requests": metrics.remaining_requests,
                    "reset_requests": metrics.reset_requests,
                    "limit_tokens": metrics.limit_tokens,
                    "remaining_tokens": metrics.remaining_tokens,
                    "reset_tokens": metrics.reset_tokens,
                },
                "error_type": metrics.error_type,
            },
        )
