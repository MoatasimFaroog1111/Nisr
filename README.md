# Super Agent Production — v0.2

A modular autonomous agent runtime that combines planning, memory, tools, subagents, verification, approvals, auditing, artifacts, web research, browser automation, Git/GitHub, databases, and deployment adapters.

## Added in v0.2

- Web research: `web_search`, `web_fetch`
- Browser automation: optional Playwright-backed `browser` tool
- Git: status/diff/log/branch plus approval-gated writes
- GitHub: repository/issues/PR reads plus approval-gated issue/comment writes
- Database: SQLite built in; PostgreSQL optional; read-only query vs approval-gated execute
- Deployment: plan/status plus approval-gated Docker build/run/stop
- Parallel subagents: researcher/architect/coder/tester/debugger via `delegate_parallel`
- Context compression: preserves recent detail and compresses older evidence/tool output to a configurable budget
- Artifact manager: persistent manifest with SHA-256 and generated artifact storage
- Approval system: persistent SQLite requests + HMAC-scoped approval tokens
- Audit log: JSONL event trail with secret/token redaction

## Architecture

```text
User / API / CLI
       |
       v
+------------------------+
| Orchestrator           |
| Plan -> Act -> Verify  |
+-----+----+----+---------+
      |    |    |
      |    |    +--> Context Compressor
      |    +------> Memory + Artifact Manager
      +-----------> Parallel Subagents
                     |
                     v
               +-----------+
               | ToolRouter|
               +-----+-----+
                     |
  +-------+------+----+----+------+--------+--------+
  | Files | Web  | Browser | Git | GitHub | DB     | Deploy
  +-------+------+---------+-----+--------+--------+-------+
                     |
             Approval + Risk Gate
                     |
                  Audit Log
```

## Quick start

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env`, configure the model provider, then:

```bash
super-agent "Inspect this workspace and explain the architecture"
uvicorn super_agent.api.app:app --host 0.0.0.0 --port 8000
```

Optional browser/database adapters:

```bash
pip install -e ".[all]"
playwright install chromium
```

## Approval flow

Mutating tools can return `metadata.approval_required` with a persistent `request_id`. Approve it through the API:

```text
POST /approvals/{request_id}/approve
```

The response contains an action-scoped `approval_token`. Pass it in the next `/run` request under `approvals` (or directly to a tool adapter). The runtime validates it against the exact pending action, so the model does not need to inspect or reproduce the token. Tokens are HMAC signed, time-limited, and payload-bound.

## API endpoints

- `GET /health`
- `POST /run`
- `GET /approvals`
- `POST /approvals/{request_id}/approve`
- `POST /approvals/{request_id}/deny`
- `GET /audit`
- `GET /artifacts`

## Safety model

- Read-only operations are generally low risk.
- Workspace/source writes, Git mutations, browser interactions, DB mutations, GitHub writes, and deployments are approval-gated.
- Catastrophic command patterns are blocked.
- Audit records redact secrets and tokens.
- Approval tokens are scoped to the exact action payload and expire.
- Database `query` rejects SQL classified as mutating.

## Notes

Browser automation requires Playwright and Chromium. PostgreSQL support requires the optional database extra. GitHub writes require `AGENT_GITHUB_TOKEN`. The provider, tools, and deployment layer are intentionally adapter-based so additional vendors can be added without changing the orchestrator.
