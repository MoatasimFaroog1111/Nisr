# Nisr Architecture

## Goal

Nisr uses Ports & Adapters to keep agent business logic independent from vendors and infrastructure. The application core knows interfaces, not OpenAI, SQLite, PostgreSQL, GitHub, Playwright, Docker, or filesystem implementation details.

## Layers

### Domain

`domain/models.py` contains agent/task/action/result models. `domain/contracts.py` contains the action protocol, system behavioral contract, and pure `RiskPolicy` domain service.

### Application

- `planning.py`: creates execution plans through `ModelProviderPort`.
- `execution.py`: parses and executes model actions through injected ports; also owns context building and subagent coordination.
- `verification.py`: performs verification using `ToolRegistryPort`.
- `orchestrator.py`: coordinates task lifecycle only.

### Ports

Small Protocol interfaces isolate the application from external systems: model provider, memory, database, audit, approval, artifact, and tool registry.

### Adapters

Concrete technology lives here. LLM, database, browser, GitHub, deployment, storage, and operational-tool components may be replaced independently.

### Infrastructure

`composition_root.py` is the assembly point. It decides which concrete adapters implement each port. `settings.py` owns environment configuration; `cli.py` is the command-line delivery surface.

### API

FastAPI is an outer delivery adapter and calls the composition root; it does not instantiate SQLite/OpenAI/GitHub classes directly.

## Dependency constraints

1. Domain must not import application, ports, adapters, infrastructure, or API.
2. Ports may import domain types only.
3. Application may import domain and ports only.
4. Adapters may import domain and ports, but not application orchestration internals.
5. Infrastructure may import all layers only for composition/wiring.
6. API may call infrastructure composition and domain DTOs as needed.

These rules are enforced by an architecture test.
