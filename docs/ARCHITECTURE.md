# Nisr Architecture

## Goal

Nisr uses Ports & Adapters to keep agent business logic independent from vendors and infrastructure. The application core knows interfaces, not OpenAI, SQLite, PostgreSQL, GitHub, Playwright, Docker, or filesystem implementation details.

## Layers

### Domain

`domain/models.py` contains agent/task/action/result models. `domain/contracts.py` contains the action protocol, system behavioral contract, and pure `RiskPolicy` domain service.

The domain explicitly models `WAITING_APPROVAL` as a first-class execution state. A protected operation is therefore paused rather than incorrectly reported as completed or generically blocked.

### Application

- `planning.py`: creates execution plans through `ModelProviderPort`.
- `execution.py`: parses and executes model actions through injected ports; also owns context building, subagent coordination, and deterministic replay of an approved paused action.
- `verification.py`: performs verification using `ToolRegistryPort`.
- `orchestrator.py`: coordinates task lifecycle, pause/resume, denial, and verification without depending on concrete persistence technology.

### Ports

Small Protocol interfaces isolate the application from external systems: model provider, memory, database, audit, approval, artifact, tool registry, and durable agent-session storage.

`SessionStorePort` allows the application to persist and recover an `AgentState` without knowing whether that state is stored in SQLite, PostgreSQL, Redis, or another adapter.

### Adapters

Concrete technology lives here. LLM, database, browser, GitHub, deployment, storage, and operational-tool components may be replaced independently.

`adapters/storage/session_sqlite.py` is the current durable session adapter. It stores agent-state snapshots and maps approval request IDs back to their originating sessions.

The browser adapter records enough context for a protected click/fill operation to be replayed after approval. On resume it can restore the approved URL before executing the exact interaction.

### Infrastructure

`composition_root.py` is the assembly point. It decides which concrete adapters implement each port. `settings.py` owns environment configuration; `cli.py` is the command-line delivery surface.

### API

FastAPI is an outer delivery adapter and calls the composition root; it does not instantiate SQLite/OpenAI/GitHub classes directly. It also serves the browser interface from `/` and keeps Swagger available at `/docs`.

Approval endpoints are workflow-aware:

- Approve: signs the request, finds the originating durable session, replays the approved operation, then resumes the same plan/session.
- Deny: marks the protected action as not executed and safely closes the same session.

### Web UI

The browser interface under `ui/` is component-based and follows the same separation principles:

- `ui/js/components/`: presentation-only components. They receive state and render markup; they do not call the backend directly.
- `ui/js/services/api-client.js`: the single HTTP boundary for `/run`, `/health`, approvals, artifacts, and audit operations.
- `ui/js/state/store.js`: client-side state management independent from individual components.
- `ui/js/utils/`: formatting and escaping helpers.
- `ui/js/app.js`: composition/controller layer that wires components, state, and services.
- `ui/styles.css`: centralized white-and-bright-gold visual design system.

No UI component is allowed to call `fetch()` directly. This boundary is enforced by `tests/test_ui.py`.

When a run enters `WAITING_APPROVAL`, the UI routes the user to Approvals. `Approve & resume` returns the resumed state from the backend and updates the same conversation without requiring the objective to be submitted again.

## Resumable approval lifecycle

```text
Objective
   |
   v
Execution -> protected tool action
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

1. Domain must not import application, ports, adapters, infrastructure, or API.
2. Ports may import domain types only.
3. Application may import domain and ports only.
4. Adapters may import domain and ports, but not application orchestration internals.
5. Infrastructure may import all layers only for composition/wiring.
6. API may call infrastructure composition and domain DTOs as needed.
7. UI components may depend on UI utilities/components only; backend access must go through the API client service.
8. UI state must remain outside presentation components.

These rules are enforced by architecture and UI boundary tests.
