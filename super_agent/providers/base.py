from __future__ import annotations

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str = "") -> str:
        raise NotImplementedError
