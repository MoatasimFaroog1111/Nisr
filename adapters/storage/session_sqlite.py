from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.models import AgentState


class SqliteSessionStore:
    """Durable agent-session snapshots and approval-to-session links."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_session_links (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_session_links_session ON approval_session_links(session_id)"
            )

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def save(self, state: AgentState, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = state.model_dump_json()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM agent_sessions WHERE session_id=?",
                (state.session_id,),
            ).fetchone()
            created_at = existing[0] if existing else now
            conn.execute(
                """
                INSERT INTO agent_sessions(session_id,state_json,status,created_at,updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json=excluded.state_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (state.session_id, payload, status, created_at, now),
            )
            conn.execute(
                "DELETE FROM approval_session_links WHERE session_id=?",
                (state.session_id,),
            )
            for request in state.pending_approvals:
                request_id = str(request.get("request_id", "")).strip()
                if request_id:
                    conn.execute(
                        """
                        INSERT INTO approval_session_links(request_id,session_id,updated_at)
                        VALUES (?,?,?)
                        ON CONFLICT(request_id) DO UPDATE SET
                            session_id=excluded.session_id,
                            updated_at=excluded.updated_at
                        """,
                        (request_id, state.session_id, now),
                    )

    def load(self, session_id: str) -> AgentState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM agent_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return AgentState.model_validate_json(row[0])

    def find_session_by_approval(self, request_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM approval_session_links WHERE request_id=?",
                (request_id,),
            ).fetchone()
        return row[0] if row else None
