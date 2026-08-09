from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from super_agent.models import RiskLevel


class ApprovalManager:
    def __init__(self, db_path: Path, secret: str, auto_approve_low_risk: bool = True):
        self.db_path = db_path
        self.secret = secret.encode("utf-8")
        self.auto_approve_low_risk = auto_approve_low_risk
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    request_id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    action_hash TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    token TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _hash_action(action_type: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps({"type": action_type, "payload": payload}, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _sign(self, request_id: str, action_hash: str, expires_at: str) -> str:
        msg = f"{request_id}:{action_hash}:{expires_at}".encode("utf-8")
        sig = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return f"apv1.{request_id}.{sig}"

    def request(self, action_type: str, payload: dict[str, Any], risk: RiskLevel, ttl_minutes: int = 30) -> dict[str, Any]:
        action_hash = self._hash_action(action_type, payload)
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request_id, status, token, expires_at FROM approvals WHERE action_hash=? ORDER BY created_at DESC LIMIT 1",
                (action_hash,),
            ).fetchone()
            if row and datetime.fromisoformat(row[3]) > now:
                return {"request_id": row[0], "status": row[1], "token": row[2], "risk": risk.value, "expires_at": row[3]}
            request_id = uuid4().hex
            expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()
            conn.execute(
                "INSERT INTO approvals(request_id, action_type, action_hash, risk, status, token, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                (request_id, action_type, action_hash, risk.value, "pending", None, now.isoformat(), expires_at),
            )
        return {"request_id": request_id, "status": "pending", "token": None, "risk": risk.value, "expires_at": expires_at}

    def approve(self, request_id: str) -> str:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute("SELECT action_hash, expires_at FROM approvals WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise KeyError("Unknown approval request")
            if datetime.fromisoformat(row[1]) <= now:
                raise ValueError("Approval request expired")
            token = self._sign(request_id, row[0], row[1])
            conn.execute("UPDATE approvals SET status='approved', token=? WHERE request_id=?", (token, request_id))
        return token

    def deny(self, request_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE approvals SET status='denied', token=NULL WHERE request_id=?", (request_id,))

    def verify(self, token: str, action_type: str, payload: dict[str, Any]) -> bool:
        if not token.startswith("apv1."):
            return False
        parts = token.split(".")
        if len(parts) != 3:
            return False
        request_id = parts[1]
        with self._connect() as conn:
            row = conn.execute(
                "SELECT action_hash, expires_at, status, token FROM approvals WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if not row or row[2] != "approved" or row[3] != token:
            return False
        if datetime.fromisoformat(row[1]) <= datetime.now(timezone.utc):
            return False
        action_hash = self._hash_action(action_type, payload)
        if not hmac.compare_digest(action_hash, row[0]):
            return False
        expected = self._sign(request_id, row[0], row[1])
        return hmac.compare_digest(expected, token)

    def authorize_or_request(self, action_type: str, payload: dict[str, Any], risk: RiskLevel, token: str = "", legacy_approvals: list[str] | None = None) -> tuple[bool, dict[str, Any] | None]:
        if risk == RiskLevel.BLOCKED:
            return False, {"status": "blocked", "risk": risk.value}
        if risk == RiskLevel.LOW and self.auto_approve_low_risk:
            return True, None
        if token and self.verify(token, action_type, payload):
            return True, None
        legacy_approvals = legacy_approvals or []
        for supplied in legacy_approvals:
            if supplied.startswith("apv1.") and self.verify(supplied, action_type, payload):
                return True, None
        if f"risk:{risk.value}" in legacy_approvals or action_type in legacy_approvals:
            return True, None
        req = self.request(action_type, payload, risk)
        return False, req

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT request_id, action_type, risk, status, created_at, expires_at FROM approvals"
        params: tuple[Any, ...]
        if status:
            sql += " WHERE status=?"
            params = (status, limit)
            sql += " ORDER BY created_at DESC LIMIT ?"
        else:
            params = (limit,)
            sql += " ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(zip(["request_id","action_type","risk","status","created_at","expires_at"], row)) for row in rows]
