from __future__ import annotations

import inspect

from domain.provider import ModelCallContext
from ports.model_provider import ModelProviderPort


def _accepts_context(provider: ModelProviderPort) -> bool:
    """Return whether a provider implements the v0.4.2 contextual call extension.

    Older provider plugins may still satisfy the original prompt/system contract.
    This compatibility check keeps them usable while new providers can opt into
    per-run telemetry by accepting the optional ``context`` keyword.
    """

    try:
        parameters = inspect.signature(provider.complete).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(
        parameter.name == "context" or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


async def complete_model(
    provider: ModelProviderPort,
    prompt: str,
    *,
    system: str = "",
    context: ModelCallContext | None = None,
) -> str:
    if _accepts_context(provider):
        return await provider.complete(prompt, system=system, context=context)
    return await provider.complete(prompt, system=system)
