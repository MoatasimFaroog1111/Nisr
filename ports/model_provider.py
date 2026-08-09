from __future__ import annotations
from typing import Protocol

class ModelProviderPort(Protocol):
    async def complete(self, prompt: str, system: str = "") -> str: ...
