from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from domain.models import RiskLevel


class SqliteApprovalRepository:
    """Persists approval requests; contains no authorization policy."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
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
                """
            )

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def find_active_by_hash(self, action_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request_id,action_type,action_hash,risk,status,token,created_at,expires_at "
                "FROM approvals WHERE action_hash=? ORDER BY created_at DESC LIMIT 1",
                (action_hash,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["request_id", "action_type", "action_hash", "risk", "status", "token", "created_at", "expires_at"],
            row,
        ))

    def create(self, action_type: str, action_hash: str, risk: RiskLevel, ttl_minutes: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        request_id = uuid4().hex
        expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO approvals(request_id,action_type,action_hash,risk,status,token,created_at,expires_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (request_id, action_type, action_hash, risk.value, "pending", None, now.isoformat(), expires_at),
            )
        return {
            "request_id": request_id,
            "action_type": action_type,
            "action_hash": action_hash,
            "risk": risk.value,
            "status": "pending",
            "token": None,
            "created_at": now.isoformat(),
            "expires_at": expires_at,
        }

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request_id,action_type,action_hash,risk,status,token,created_at,expires_at FROM approvals WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["request_id", "action_type", "action_hash", "risk", "status", "token", "created_at", "expires_at"],
            row,
        ))

    def set_approved(self, request_id: str, token: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE approvals SET status='approved', token=? WHERE request_id=?", (token, request_id))

    def set_denied(self, request_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE approvals SET status='denied', token=NULL WHERE request_id=?", (request_id,))

    def list(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        sql = "SELECT request_id,action_type,risk,status,created_at,expires_at FROM approvals"
        params: tuple[Any, ...]
        if status:
            sql += " WHERE status=? ORDER BY created_at DESC LIMIT ?"
            params = (status, limit)
        else:
            sql += " ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        keys = ["request_id", "action_type", "risk", "status", "created_at", "expires_at"]
        return [dict(zip(keys, row)) for row in rows]


class HmacApprovalTokenService:
    """Signs/verifies action-scoped tokens; knows nothing about SQLite."""

    def __init__(self, secret: str):
        self._secret = secret.encode("utf-8")

    @staticmethod
    def action_hash(action_type: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            {"type": action_type, "payload": payload},
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def sign(self, request_id: str, action_hash: str, expires_at: str) -> str:
        message = f"{request_id}:{action_hash}:{expires_at}".encode("utf-8")
        signature = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        return f"apv1.{request_id}.{signature}"

    def matches(self, token: str, request: dict[str, Any]) -> bool:
        if not token.startswith("apv1.") or len(token.split(".")) != 3:
            return False
        expected = self.sign(request["request_id"], request["action_hash"], request["expires_at"])
        return hmac.compare_digest(expected, token)


class ApprovalService:
    """Authorization policy coordinating an approval repository and token signer."""

    def __init__(
        self,
        repository: SqliteApprovalRepository,
        tokens: HmacApprovalTokenService,
        auto_approve_low_risk: bool = True,
        presented_approvals: list[str] | None = None,
    ):
        self._repository = repository
        self._tokens = tokens
        self._auto_approve_low_risk = auto_approve_low_risk
        self._presented_approvals = list(presented_approvals or [])

    def request(self, action_type: str, payload: dict[str, Any], risk: RiskLevel, ttl_minutes: int = 30) -> dict[str, Any]:
        action_hash = self._tokens.action_hash(action_type, payload)
        existing = self._repository.find_active_by_hash(action_hash)
        now = datetime.now(timezone.utc)
        if existing and datetime.fromisoformat(existing["expires_at"]) > now:
            return {
                "request_id": existing["request_id"],
                "status": existing["status"],
                "token": existing["token"],
                "risk": risk.value,
                "expires_at": existing["expires_at"],
            }
        row = self._repository.create(action_type, action_hash, risk, ttl_minutes)
        return {
            "request_id": row["request_id"],
            "status": row["status"],
            "token": None,
            "risk": risk.value,
            "expires_at": row["expires_at"],
        }

    def approve(self, request_id: str) -> str:
        row = self._repository.get(request_id)
        if not row:
            raise KeyError("Unknown approval request")
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            raise ValueError("Approval request expired")
        token = self._tokens.sign(request_id, row["action_hash"], row["expires_at"])
        self._repository.set_approved(request_id, token)
        return token

    def deny(self, request_id: str) -> None:
        self._repository.set_denied(request_id)

    def verify(self, token: str, action_type: str, payload: dict[str, Any]) -> bool:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        row = self._repository.get(parts[1])
        if not row or row["status"] != "approved" or row["token"] != token:
            return False
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            return False
        if self._tokens.action_hash(action_type, payload) != row["action_hash"]:
            return False
        return self._tokens.matches(token, row)

    def authorize_or_request(
        self,
        action_type: str,
        payload: dict[str, Any],
        risk: RiskLevel,
        token: str = "",
        legacy_approvals: list[str] | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        if risk == RiskLevel.BLOCKED:
            return False, {"status": "blocked", "risk": risk.value}
        if risk == RiskLevel.LOW and self._auto_approve_low_risk:
            return True, None
        if token and self.verify(token, action_type, payload):
            return True, None
        supplied_approvals = list(legacy_approvals or []) + self._presented_approvals
        for supplied in supplied_approvals:
            if supplied.startswith("apv1.") and self.verify(supplied, action_type, payload):
                return True, None
            if supplied in {f"risk:{risk.value}", action_type}:
                return True, None
        return False, self.request(action_type, payload, risk)

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._repository.list(status, limit)
