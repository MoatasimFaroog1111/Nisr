from __future__ import annotations

import asyncio
from typing import Any


class PostgresDatabaseAdapter:
    def __init__(self, url: str):
        self._url = url

    def _run_sync(self, sql: str, params: list[Any], query: bool):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError('PostgreSQL support requires: pip install -e ".[database]"') from exc
        with psycopg.connect(self._url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params or None)
                if query:
                    columns = [item.name for item in cursor.description or []]
                    return [dict(zip(columns, row)) for row in cursor.fetchmany(1000)]
                conn.commit()
                return {"rowcount": cursor.rowcount}

    async def query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._run_sync, sql, params, True)

    async def execute(self, sql: str, params: list[Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._run_sync, sql, params, False)
