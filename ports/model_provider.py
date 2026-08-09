from __future__ import annotations

from typing import Protocol

from domain.provider import ModelCallContext


class ModelProviderPort(Protocol):
    async def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        context: ModelCallContext | None = None,
    ) -> str: ...
