from __future__ import annotations

from typing import Any

from adapters.browser.playwright import BrowserSession
from infrastructure.settings import Settings, settings as default_settings


async def readiness_snapshot(settings: Settings = default_settings) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    provider_ok = bool(settings.provider and settings.model and settings.api_key and settings.api_base)
    checks["provider_configuration"] = {
        "ok": provider_ok,
        "provider": settings.provider,
        "model": settings.model or None,
    }

    session = BrowserSession(settings.artifacts_dir)
    try:
        browser = await session.probe()
        checks["browser"] = browser
    except Exception as exc:
        checks["browser"] = {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    finally:
        await session.close()

    ok = all(bool(check.get("ok")) for check in checks.values())
    return {
        "ok": ok,
        "service": "nisr",
        "version": "0.3.1",
        "checks": checks,
    }
