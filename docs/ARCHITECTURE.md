# Architecture v0.2

## Control plane

`Orchestrator` owns the agent state machine and is the only component that decides when a task is planned, executed, verified, blocked, or delivered. It depends on interfaces rather than vendor SDKs.

## Intelligence plane

- `Planner`: converts objectives into verifiable tasks.
- `ContextManager` + `ContextCompressor`: preserves goal, plan, recent evidence and tool results inside a bounded context budget.
- `SubagentManager`: executes specialist roles and supports bounded `asyncio` parallelism.
- `MemoryStore`: persistent SQLite durable memory.

## Execution plane

`ToolRouter` exposes narrowly scoped adapters:

- Files and shell
- Web search and fetch
- Browser automation
- Git and GitHub
- Database
- Deployment
- Artifact management
- Approval status

## Trust plane

- `RiskGate` classifies shell, file, and SQL operations.
- `ApprovalManager` persists approval requests and issues HMAC-signed, payload-bound, expiring tokens.
- `AuditLog` records execution events as JSONL while redacting secrets/tokens.
- `VerificationEngine` executes low-risk verification commands after task completion.

## Extension rule

New vendors should be introduced as provider/tool adapters. Do not import vendor-specific SDKs into the orchestrator.
