# Nisr v0.3

Nisr is a modular autonomous-agent runtime refactored around **SOLID**, **component-based design**, and **Ports & Adapters (Hexagonal Architecture)**.

## Architecture

```text
Nisr/
├── domain/
│   ├── models.py
│   └── contracts.py
├── application/
│   ├── orchestrator.py
│   ├── execution.py
│   ├── planning.py
│   └── verification.py
├── ports/
│   ├── model_provider.py
│   ├── memory.py
│   ├── database.py
│   ├── audit.py
│   ├── approval.py
│   ├── artifact.py
│   └── tool.py
├── adapters/
│   ├── llm/
│   ├── database/
│   ├── browser/
│   ├── github/
│   ├── deployment/
│   ├── storage/
│   └── tools/
├── infrastructure/
│   ├── composition_root.py
│   ├── settings.py
│   └── cli.py
└── api/
    └── app.py
```

## Dependency rule

The direction is one-way:

```text
Domain <- Ports <- Application <- Infrastructure/Adapters/API
```

More precisely:

- `domain` imports no application, adapter, API, or infrastructure code.
- `application` depends only on `domain` and `ports`.
- `ports` define contracts and contain no vendor implementations.
- `adapters` implement the ports or tool contract for OpenAI-compatible LLMs, SQLite/PostgreSQL, Playwright, GitHub, Docker, filesystem, shell, Git, and web operations.
- `infrastructure/composition_root.py` is the only module responsible for choosing concrete implementations and wiring them together.
- `api` is a delivery adapter; it does not build business rules itself.

## SOLID mapping

- **SRP:** planning, execution, verification, orchestration, persistence, token signing, and vendor integrations are separated.
- **OCP:** new LLM/database/tool adapters can be added without editing application use-cases.
- **LSP:** concrete adapters satisfy small Protocol contracts.
- **ISP:** separate ports exist for model, memory, database, audit, approvals, artifacts, and tools.
- **DIP:** application services receive ports via constructor injection; no OpenAI/SQLite/GitHub/Docker imports exist in the application layer.

## Components

Nisr currently supports:

- Planner and task lifecycle orchestration
- Autonomous action execution
- Multi-agent parallel delegation
- Context compression
- Persistent memory
- Risk classification and approval gating
- Audit logs with secret redaction
- Artifact storage with SHA-256 manifests
- File, shell, web, Git, browser, GitHub and deployment tools
- SQLite and PostgreSQL database adapters
- OpenAI-compatible model adapter
- CLI and FastAPI delivery surfaces

## Quick start

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -e ".[dev]"
```

Copy `.env.example` to `.env`, configure `AGENT_MODEL` and `AGENT_API_KEY`, then run:

```bash
nisr "Inspect this workspace and explain the architecture"
```

API:

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

Optional integrations:

```bash
pip install -e ".[all]"
playwright install chromium
```

## Extending Nisr

To add another LLM, implement `ModelProviderPort` in `adapters/llm/` and wire it in the composition root. To add MySQL, implement `DatabasePort` in `adapters/database/`; `DatabaseTool` does not need modification. Other capabilities can be added as tools implementing the `ToolPort` shape and registered in the composition root.
