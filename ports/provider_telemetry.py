from __future__ import annotations

from typing import Protocol

from domain.provider import ProviderCallMetrics


class ProviderTelemetryPort(Protocol):
    def record(self, metrics: ProviderCallMetrics) -> None: ...
