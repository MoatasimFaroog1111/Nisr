from __future__ import annotations

from super_agent.config import Settings
from super_agent.providers.base import ModelProvider
from super_agent.providers.openai_compatible import OpenAICompatibleProvider


def build_provider(settings: Settings) -> ModelProvider:
    if settings.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            api_base=settings.api_base,
            api_key=settings.api_key,
            model=settings.model,
        )
    raise ValueError(f"Unsupported provider: {settings.provider}")
