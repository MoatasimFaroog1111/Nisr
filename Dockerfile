FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md ./
COPY domain ./domain
COPY application ./application
COPY ports ./ports
COPY adapters ./adapters
COPY infrastructure ./infrastructure
COPY api ./api
COPY ui ./ui
COPY config ./config
COPY docs ./docs
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip setuptools wheel \
    && pip install '.[browser]' \
    && python -m playwright install --with-deps chromium

RUN useradd --create-home --uid 10001 nisr \
    && mkdir -p /app/workspace /app/data /app/artifacts /ms-playwright \
    && chmod 0755 /app/docker-entrypoint.sh \
    && chown -R nisr:nisr /app /ms-playwright

ENV AGENT_WORKSPACE=/app/workspace \
    AGENT_MEMORY_DB=/app/data/agent_memory.sqlite3 \
    AGENT_APPROVAL_DB=/app/data/approvals.sqlite3 \
    AGENT_SESSION_DB=/app/data/sessions.sqlite3 \
    AGENT_BROWSER_SESSION_DB=/app/data/browser_sessions.sqlite3 \
    AGENT_AUDIT_LOG=/app/data/audit.jsonl \
    AGENT_ARTIFACTS_DIR=/app/artifacts

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
