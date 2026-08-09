from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any


class SqliteDatabaseAdapter:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _query_sync(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(sql, params)
            columns = [item[0] for item in cursor.description or []]
            return [dict(zip(columns, row)) for row in cursor.fetchmany(1000)]

    def _execute_sync(self, sql: str, params: list[Any]) -> dict[str, Any]:
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return {"rowcount": cursor.rowcount}

    async def query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._query_sync, sql, params)

    async def execute(self, sql: str, params: list[Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._execute_sync, sql, params)
