from __future__ import annotations

import pytest

from adapters.browser.reliable_playwright import ReliablePlaywrightBrowserProvider
from domain.browser import BrowserState
from domain.browser_reliability import BrowserReliabilityPolicy


def test_reliability_policy_never_replays_state_changing_actions():
    policy = BrowserReliabilityPolicy()
    assert policy.max_attempts("navigate") == 2
    assert policy.max_attempts("view") == 2
    assert policy.max_attempts("click") == 1
    assert policy.max_attempts("input") == 1
    assert policy.max_attempts("selectOption") == 1


def test_semantic_locator_syntax_is_vendor_adapter_detail():
    parse = ReliablePlaywrightBrowserProvider._semantic_expression
    assert parse("role=link|name=Pricing") == ("role", "link", "Pricing")
    assert parse("text=Pricing") == ("text", "Pricing", None)
    assert parse("label=Email") == ("label", "Email", None)
    assert parse("testid=submit") == ("testid", "submit", None)
    assert parse("#pricing") is None


@pytest.mark.asyncio
async def test_safe_action_retries_once_and_records_attempt():
    provider = ReliablePlaywrightBrowserProvider()
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient read failure")
        return BrowserState(session_id="s", url="https://example.test")

    state = await provider._safe_call("view", operation)
    assert calls == 2
    assert state.reliability["attempt"] == 2
    assert state.reliability["safe_retry"] is True


@pytest.mark.asyncio
async def test_state_changing_action_is_not_replayed_after_failure():
    provider = ReliablePlaywrightBrowserProvider()
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        raise RuntimeError("ambiguous click outcome")

    with pytest.raises(RuntimeError):
        await provider._safe_call("click", operation)
    assert calls == 1
