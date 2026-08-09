from pathlib import Path

from api.errors import _upstream_classification
from adapters.browser.playwright_provider import PlaywrightBrowserProvider


def test_upstream_error_classification_is_structured():
    assert _upstream_classification(403)[:2] == (502, "upstream_auth_error")
    assert _upstream_classification(429)[:2] == (503, "upstream_rate_limited")
    assert _upstream_classification(500)[:2] == (502, "upstream_service_error")


def test_browser_provider_blocks_obvious_local_targets():
    assert not PlaywrightBrowserProvider._url_allowed("file:///etc/passwd")
    assert not PlaywrightBrowserProvider._url_allowed("http://localhost:8000")
    assert not PlaywrightBrowserProvider._url_allowed("http://127.0.0.1")
    assert not PlaywrightBrowserProvider._url_allowed("http://169.254.169.254/latest/meta-data")
    assert not PlaywrightBrowserProvider._url_allowed("http://10.0.0.8")
    assert PlaywrightBrowserProvider._url_allowed("https://example.com")


def test_railway_image_installs_browser_runtime():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "pip install '.[browser]'" in dockerfile
    assert "playwright install --with-deps chromium" in dockerfile
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile
    assert "USER nisr" in dockerfile
