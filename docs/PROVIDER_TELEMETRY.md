# Provider Telemetry and Run Token Budget

Nisr v0.4.2 keeps provider diagnostics and token-budget policy outside Agent Core.

## Flow

```text
Planning / Agent Step / Subagent
        |
        v
ModelProviderPort + ModelCallContext(session_id, purpose)
        |
        v
OpenAICompatibleAdapter
        |
        +--> normalized ProviderCallMetrics --> ProviderTelemetryPort --> Audit
        |
        +--> normalized ProviderCallMetrics --> TokenBudgetPort --> RunTokenBudgetManager
                                                   |
                                                   +--> proactive delay near provider reset
                                                   +--> dynamic context character budget
```

The adapter parses provider-specific headers. The application layer sees only normalized metrics and never imports `httpx` or OpenAI-specific header names.

## Recorded telemetry

`provider.telemetry` audit events may contain:

- request id
- HTTP status
- purpose (`planning`, `agent_step`, `subagent:<role>`)
- attempt / retry flag
- prompt/completion/total token counts
- request limit / remaining / reset
- token limit / remaining / reset
- normalized error type

Prompts, model responses, API keys, authorization headers and browser credentials are not part of the telemetry contract.

## Run token budget

`RunTokenBudgetManager` is a soft per-run/session guard. It tracks normalized provider usage and computes a dynamic context ceiling from both:

1. the configured Nisr run token budget, and
2. the latest provider remaining-token window.

When the provider remaining-token window is too small for the estimated next input plus the configured reserve, the provider adapter waits for the normalized reset duration before issuing the next request. When the run or provider token headroom shrinks, `ContextBuilder` compresses older tool results, evidence, memories and long tool descriptions before the next model call.

## Configuration

```text
AGENT_PROVIDER_MAX_RETRIES=2
AGENT_PROVIDER_RETRY_BASE_SECONDS=0.8
AGENT_RUN_TOKEN_BUDGET=24000
AGENT_PROVIDER_TOKEN_RESERVE=4000
AGENT_TOKEN_CHARS_PER_TOKEN=4.0
AGENT_MIN_CONTEXT_BUDGET_CHARS=8000
AGENT_CONTEXT_BUDGET_SAFETY_RATIO=0.65
AGENT_CONTEXT_BUDGET_CHARS=50000
```

These are policy defaults, not hard-coded provider limits. Actual provider limits remain authoritative and are learned from normalized response telemetry when available.

## SOLID boundaries

- **SRP:** provider HTTP parsing, telemetry persistence, budgeting, context compression and orchestration are separate responsibilities.
- **OCP:** a future Responses API, Claude or Gemini adapter can emit the same normalized metrics without changing Agent Core.
- **LSP:** all providers still satisfy `ModelProviderPort`.
- **ISP:** telemetry and token budgeting use separate ports.
- **DIP:** application code depends on `ModelProviderPort` and `TokenBudgetPort`; infrastructure chooses concrete implementations.
