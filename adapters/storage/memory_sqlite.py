from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SqliteMemoryAdapter:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)")

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def upsert(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM memories WHERE key=? ORDER BY id DESC LIMIT 1", (key,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE memories SET value=?, updated_at=? WHERE id=?",
                    (value, now, row[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO memories(key,value,created_at,updated_at) VALUES (?,?,?,?)",
                    (key, value, now, now),
                )

    def search(self, query: str, limit: int = 8) -> list[str]:
        q = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key,value FROM memories
                WHERE key LIKE ? OR value LIKE ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (q, q, limit),
            ).fetchall()
        return [f"{key}: {value}" for key, value in rows]

    def all(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key,value,created_at,updated_at FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"key": r[0], "value": r[1], "created_at": r[2], "updated_at": r[3]}
            for r in rows
        ]
