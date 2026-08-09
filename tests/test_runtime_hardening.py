from pathlib import Path

import pytest

from adapters.browser.playwright import PlaywrightBrowserTool
from api.errors import _upstream_classification


class _FailingBrowserSession:
    page = None

    async def ensure(self):
        raise RuntimeError("chromium missing")

    async def close(self):
        return None


class _Approvals:
    def authorize_or_request(self, *args, **kwargs):
        return True, None


def test_upstream_error_classification_is_structured():
    assert _upstream_classification(403)[:2] == (502, "upstream_auth_error")
    assert _upstream_classification(429)[:2] == (503, "upstream_rate_limited")
    assert _upstream_classification(500)[:2] == (502, "upstream_service_error")


@pytest.mark.asyncio
async def test_browser_runtime_failure_becomes_tool_result():
    tool = PlaywrightBrowserTool(_FailingBrowserSession(), _Approvals())
    result = await tool.run({"operation": "open", "url": "https://example.com"})
    assert not result.ok
    assert "Browser operation failed" in result.error
    assert result.metadata["error_type"] == "RuntimeError"


def test_railway_image_installs_browser_runtime():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "pip install '.[browser]'" in dockerfile
    assert "playwright install --with-deps chromium" in dockerfile
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile
    assert "USER nisr" in dockerfile
