# Nisr Architecture

## Goal

Nisr uses Ports & Adapters to keep agent business logic independent from vendors and infrastructure. The application core knows interfaces, not OpenAI, SQLite, PostgreSQL, GitHub, Playwright, Docker, WebSocket, or filesystem implementation details.

## Layers

### Domain

`domain/models.py` contains agent/task/action/result models. `domain/contracts.py` contains the action protocol, system behavioral contract, and pure `RiskPolicy` domain service.

The domain models protected pauses as first-class state. `WAITING_APPROVAL` pauses an authorization-gated action; `WAITING_USER` pauses an agent run when the same browser session must be handed to the user. `AgentRunStatus` is independent from UI presentation and includes `RUNNING`, `WAITING_TOOL`, `WAITING_USER`, `COMPLETED`, `FAILED`, and `CANCELLED`.

Browser-specific domain values live in `domain/browser.py`: browser state, tabs, frames, events, ownership and control-state enums. They contain no Playwright or FastAPI types.

### Application

- `planning.py`: creates execution plans through `ModelProviderPort`.
- `execution.py`: parses and executes model actions through injected ports; also owns context building, subagent coordination, redacted tool-state capture, and deterministic replay of an approved paused action.
- `verification.py`: performs verification using `ToolRegistryPort`.
- `orchestrator.py`: coordinates task lifecycle, approval pause/resume, user-takeover pause/resume, denial, and verification without depending on concrete persistence or browser technology.
- `browser_runtime.py`: owns logical browser sessions, ownership locking, Browser Service use cases, takeover transitions, user/agent action serialization, inactivity cleanup and browser recovery signals. It imports only domain models and browser/realtime ports.
- `browser_streaming.py`: maintains one frame publisher per active browser session regardless of viewer count. A disconnected viewer stops streaming but does not close the browser session.

### Ports

Small Protocol interfaces isolate the application from external systems: model provider, memory, database, audit, approval, artifact, tool registry, durable agent-session storage, browser provider and realtime browser-event publishing.

`SessionStorePort` allows the application to persist and recover an `AgentState` without knowing whether that state is stored in SQLite, PostgreSQL, Redis, or another adapter.

`BrowserProvider` defines browser capabilities such as create session, navigate, view, click, input, keyboard, scroll, select, history navigation, tabs, frame capture and close. `CdpBrowserProvider` is a separate optional capability interface so Chromium-specific diagnostics do not pollute the generic browser contract.

### Adapters

Concrete technology lives here. LLM, database, browser, GitHub, deployment, storage, realtime and operational-tool components may be replaced independently.

`adapters/browser/playwright_provider.py` is the current `BrowserProvider` implementation. Playwright owns Chromium mechanics behind the port; the agent never imports or calls Playwright. Each logical browser session receives its own Chromium browser context so cookies, local storage, session storage and tabs remain isolated between sessions while surviving agent/user control transitions.

The provider blocks obvious local/private navigation targets, runs in the non-root Railway container, does not use `--no-sandbox`, captures JPEG viewport frames, detects credential/OTP/payment/CAPTCHA signals, refuses agent input into sensitive fields and exposes an optional CDP diagnostic snapshot.

`adapters/tools/browser.py` exposes the existing Tool Registry entries:

- `browser.navigate`
- `browser.view`
- `browser.click`
- `browser.input`
- `browser.pressKey`
- `browser.scroll`
- `browser.selectOption`
- `browser.back`
- `browser.forward`
- `browser.refresh`
- `browser.getTabs`
- `browser.switchTab`
- `browser.closeTab`
- `browser.requestTakeover`

A compatibility `browser` facade still routes legacy operation names through the same Browser Service; there is no parallel browser architecture.

`adapters/realtime/browser_events.py` is the current transport-neutral process-local event hub. `api/browser.py` is the WebSocket delivery gateway that subscribes to this hub. Replacing the hub with Redis/NATS later does not change Browser Service or browser tools.

### Infrastructure

`composition_root.py` is the assembly point. It decides which concrete adapters implement each port. `settings.py` owns environment configuration; `cli.py` is the command-line delivery surface.

The browser runtime is application-scoped: one provider/runtime is shared by requests while each session has isolated ownership and browser context. Runtime cleanup is controlled by inactivity timeout rather than WebSocket disconnect.

### API / Realtime

FastAPI is an outer delivery adapter and calls the composition root; it does not instantiate browser mechanics in the agent core. It serves the UI from `/`, Swagger from `/docs`, browser-session HTTP endpoints, and an authenticated WebSocket at `/ws/browser/{session_id}`.

Browser access uses a short-lived HMAC session token bound to both `session_id` and the anonymous/browser user cookie. Backend ownership checks are authoritative; frontend commands are never trusted merely because the button is visible.

The realtime channel carries status/action/frame events such as:

- `browser.started`
- `browser.navigating`
- `browser.loaded`
- `browser.frame`
- `browser.url_changed`
- `browser.action`
- `browser.control_changed`
- `browser.closed`
- `browser.error`
- `user_takeover_requested`

The frame streamer sends screenshot frames separately from agent reasoning. No chain-of-thought is exposed.

### Web UI

The interface under `ui/` remains component-based:

- `ui/js/components/`: presentation-only components.
- `ui/js/components/computer-panel.js`: Chat-adjacent Computer composition.
- `browser-viewer.js`: live frame surface.
- `browser-controls.js`: address/navigation/takeover/private-input controls.
- `browser-status.js`: connection and ownership status.
- `browser-activity.js`: user-facing browser actions/status only, never private reasoning.
- `ui/js/services/api-client.js`: HTTP boundary.
- `ui/js/services/browser-socket.js`: WebSocket/reconnect boundary.
- `ui/js/state/store.js`: UI state independent from components.
- `ui/js/app.js`: composition/controller wiring only.
- `ui/styles.css`: centralized white-and-bright-gold design system.

Components never call `fetch()` or `WebSocket` directly. These boundaries are enforced by `tests/test_ui.py`.

Frames use a fast DOM update path so a 1–2 FPS browser stream does not rebuild the entire Chat view. URL, tabs, ownership, activity and lifecycle events update normal store state.

## Browser control lifecycle

```text
Agent RUNNING
    |
    v
browser.* tool -> BrowserService -> BrowserProvider -> Chromium
    |
    +--> browser events/frames -> realtime publisher -> WebSocket -> Computer Panel
    |
Sensitive step detected
    |
    v
WAITING_USER + user_takeover_requested
    |
User presses Take Control
    |
    v
TRANSITIONING -> USER_CONTROL
    |
    +--> same browser context
    +--> same cookies/localStorage/sessionStorage
    +--> same URL/tabs/history
    +--> agent browser calls return BROWSER_CONTROLLED_BY_USER
    |
User completes login / CAPTCHA / OTP / payment confirmation
    |
User presses Return Control to Agent
    |
    v
TRANSITIONING -> AGENT_CONTROL
    |
    +--> current URL/tabs/state captured
    +--> observation appended to same AgentState
    +--> same task becomes runnable
    |
    v
RUNNING -> verification -> COMPLETED/FAILED
```

An `asyncio.Lock` on each logical Browser Session serializes ownership changes and actions. Agent and user cannot operate the same browser concurrently.

## Sensitive-data policy

Credentials, OTPs, card data and private takeover text must not enter agent memory, audit arguments, browser activity events or persisted `AgentState`.

- Agent `browser.input` arguments are redacted before audit/state capture.
- Browser-tool output is excluded from audit previews.
- Sensitive pages return only a minimal observation to the agent; page text/interactables are removed and the run transitions to `WAITING_USER`.
- User takeover text goes directly from the authenticated WebSocket to the focused Chromium page and browser events record only character count/action type.
- Browser frames remain visible to the owning user but are not written to the audit log.

## Failure and timeout policy

A viewer WebSocket disconnect does not close Chromium. The session remains available until the configured inactivity timeout. Active viewers keep the session alive through frame capture activity.

When the provider reports that its browser process/session disappeared, Browser Service attempts to recreate the runtime context and emits `browser.error` with `browser_state_changed=true`. It does not silently retry potentially state-changing clicks or inputs, preventing duplicate side effects. The agent receives the failed tool result and can recover using fresh browser evidence.

## Resumable approval lifecycle

```text
Objective
   |
   v
Execution -> protected non-browser tool action
   |
   v
WAITING_APPROVAL
   |
   +--> durable AgentState snapshot
   +--> approval request -> session link
   |
User decision
   |
   +--> Deny ----> protected action NOT executed -> DELIVERY/BLOCKED
   |
   +--> Approve -> signed action-scoped token
                    |
                    v
              replay exact action
                    |
                    v
              continue same plan
                    |
                    v
                verification
                    |
                    v
                 DELIVERY
```

The approval token remains action-scoped and time-limited. Approval does not become a global permission for unrelated actions.

## Dependency constraints

1. Domain must not import application, ports, adapters, infrastructure, API, or UI.
2. Ports may import domain types only.
3. Application may import domain and ports only.
4. Adapters may implement ports and use application services where they are delivery/tool adapters, but agent orchestration never imports concrete adapters.
5. Playwright is confined to the browser adapter; Browser Service and agent core never import it.
6. WebSocket is confined to the API/UI service boundary; Browser Service only publishes through `BrowserEventPublisherPort`.
7. Infrastructure may import all layers only for composition/wiring.
8. API may call infrastructure composition and application use cases; it does not implement browser mechanics.
9. UI components may depend on UI utilities/components only; HTTP and WebSocket access go through services.
10. UI state remains outside presentation components.

These rules are enforced by architecture, browser-takeover and UI boundary tests.
