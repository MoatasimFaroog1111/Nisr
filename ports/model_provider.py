from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelCallContext:
    """Vendor-neutral metadata for one model call; never contains prompt or secrets."""

    session_id: str = ""
    purpose: str = "agent"


class ModelProviderPort(Protocol):
    async def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        context: ModelCallContext | None = None,
    ) -> str: ...
