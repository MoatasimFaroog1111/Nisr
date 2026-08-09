# Deploy Nisr on Railway

Nisr is prepared for Railway with a root `Dockerfile`, `railway.toml`, and `/health` endpoint.

## Source

Connect the GitHub repository:

`MoatasimFaroog1111/Nisr`

Railway will detect the root Dockerfile automatically. The deployment configuration sets `/health` as the healthcheck path.

## Required variables for agent execution

The API can boot and serve `/health` without an LLM key. To use `POST /run`, configure:

- `AGENT_PROVIDER=openai_compatible`
- `AGENT_MODEL=<model-name>`
- `AGENT_API_BASE=<OpenAI-compatible-base-url>`
- `AGENT_API_KEY=<secret>`
- `AGENT_APPROVAL_SECRET=<long-random-secret>`

Optional integrations:

- `AGENT_GITHUB_TOKEN`
- `AGENT_DATABASE_URL`
- `AGENT_MAX_STEPS`
- `AGENT_CONTEXT_BUDGET_CHARS`

Do not commit real secrets to GitHub.

## Health verification

Expected response from `GET /health`:

```json
{"ok": true, "service": "nisr", "version": "0.3.0"}
```

## Persistence

The default local paths are under `/app/data`, `/app/artifacts`, and `/app/workspace`. Railway service filesystem storage is ephemeral unless a persistent volume is mounted. For production use, attach a Railway volume and map the data paths to it, or replace the storage adapters with external persistent services.

## Optional browser adapter

The base deployment keeps browser automation optional. If browser automation is required in the Railway image, install the `browser` extra and Chromium in the image. The current adapter fails gracefully with an explicit installation message if Playwright is not available.
