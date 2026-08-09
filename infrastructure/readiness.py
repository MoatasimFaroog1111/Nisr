from __future__ import annotations

from typing import Any

from adapters.browser.playwright_provider import PlaywrightBrowserProvider
from infrastructure.settings import Settings, settings as default_settings


async def readiness_snapshot(
    settings: Settings = default_settings,
    browser_provider: PlaywrightBrowserProvider | None = None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    provider_ok = bool(settings.provider and settings.model and settings.api_key and settings.api_base)
    checks["provider_configuration"] = {
        "ok": provider_ok,
        "provider": settings.provider,
        "model": settings.model or None,
    }

    owned_provider = browser_provider is None
    provider = browser_provider or PlaywrightBrowserProvider()
    try:
        checks["browser"] = await provider.probe()
    except Exception as exc:
        checks["browser"] = {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    finally:
        if owned_provider:
            await provider.close_all()

    ok = all(bool(check.get("ok")) for check in checks.values())
    return {
        "ok": ok,
        "service": "nisr",
        "version": "0.4.0",
        "checks": checks,
    }
