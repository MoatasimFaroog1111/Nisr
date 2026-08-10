from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrowserReliabilityPolicy:
    """Pure policy defining which browser actions may be replayed after a transient failure."""

    safe_retry_actions: frozenset[str] = frozenset({
        "navigate",
        "view",
        "back",
        "forward",
        "refresh",
        "getTabs",
        "switchTab",
    })

    def max_attempts(self, action: str) -> int:
        return 2 if action in self.safe_retry_actions else 1

    def safe_to_retry(self, action: str) -> bool:
        return action in self.safe_retry_actions
