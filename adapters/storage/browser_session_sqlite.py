from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from domain.browser_session import BrowserSessionSnapshot


class SqliteBrowserSessionStore:
    """Durable browser snapshots. Storage-state payload is operational state, never audit data."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS browser_session_snapshots (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    updated_at_epoch REAL NOT NULL,
                    expires_at_epoch REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_browser_snapshot_expiry ON browser_session_snapshots(expires_at_epoch)"
            )
        try:
            os.chmod(self._db_path, 0o600)
        except OSError:
            pass

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def save(self, snapshot: BrowserSessionSnapshot) -> None:
        payload = snapshot.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_session_snapshots(session_id,user_id,snapshot_json,updated_at_epoch,expires_at_epoch)
                VALUES (?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    snapshot_json=excluded.snapshot_json,
                    updated_at_epoch=excluded.updated_at_epoch,
                    expires_at_epoch=excluded.expires_at_epoch
                """,
                (
                    snapshot.session_id,
                    snapshot.user_id,
                    payload,
                    snapshot.updated_at_epoch,
                    snapshot.expires_at_epoch,
                ),
            )

    def load(self, session_id: str) -> BrowserSessionSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM browser_session_snapshots WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return BrowserSessionSnapshot.model_validate_json(row[0]) if row else None

    def delete(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM browser_session_snapshots WHERE session_id=?", (session_id,))

    def purge_expired(self, now_epoch: float) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM browser_session_snapshots WHERE expires_at_epoch <= ?",
                (float(now_epoch),),
            )
            return int(cursor.rowcount or 0)
