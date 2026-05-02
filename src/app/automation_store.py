"""Automation persistence for auth, service accounts, jobs, approvals, and audit events."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.app.redaction import redact_value


def _sanitize_payload(payload: Any) -> Any:
    return redact_value(payload)


def _json_dumps(payload: Any) -> str:
    return json.dumps(_sanitize_payload(payload), ensure_ascii=True, sort_keys=True)


class AutomationStore:
    """SQLite-backed store for auth, automation execution, and audit data."""

    _local = threading.local()

    def __init__(self, sqlite_path: str):
        self.sqlite_path = str(Path(sqlite_path))
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()
        self._set_wal_mode()

    def _connect(self) -> sqlite3.Connection:
        cached_path = getattr(self._local, "conn_path", None)
        conn = getattr(self._local, "conn", None)
        if conn is not None and cached_path == self.sqlite_path:
            try:
                conn.execute("SELECT 1")
                conn.row_factory = sqlite3.Row
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._local.conn = conn
        self._local.conn_path = self.sqlite_path
        return conn

    def _set_wal_mode(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_login_at REAL,
                    disabled_at REAL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
                ON sessions(token_hash);
                CREATE INDEX IF NOT EXISTS idx_sessions_username
                ON sessions(username, created_at DESC);

                CREATE TABLE IF NOT EXISTS service_accounts (
                    account_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    description TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL,
                    revoked_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_service_accounts_token_hash
                ON service_accounts(token_hash);

                CREATE TABLE IF NOT EXISTS automation_jobs (
                    job_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    principal_type TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    input_payload TEXT NOT NULL,
                    result_payload TEXT,
                    error_payload TEXT,
                    approval_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_automation_jobs_principal
                ON automation_jobs(principal_type, principal_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS automation_approvals (
                    approval_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    principal_type TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    input_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision_reason TEXT,
                    decided_by TEXT,
                    job_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    decided_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_automation_approvals_status
                ON automation_approvals(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id TEXT PRIMARY KEY,
                    principal_type TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    args_hash TEXT NOT NULL,
                    outcome_status TEXT NOT NULL,
                    approval_state TEXT,
                    envelope TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_events_idempotency
                ON audit_events(principal_type, principal_id, operation_id, idempotency_key, created_at DESC);
                """
            )
            conn.commit()

    @staticmethod
    def _decode_json_row(row: sqlite3.Row, field: str) -> Dict[str, Any]:
        value = row[field]
        return json.loads(value) if value else {}

    def has_users(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM users
                WHERE disabled_at IS NULL
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    def upsert_user(self, username: str, password_hash: str, role: str) -> Dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(username, password_hash, role, created_at, updated_at, last_login_at, disabled_at)
                VALUES (?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(username)
                DO UPDATE SET
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    updated_at = excluded.updated_at,
                    disabled_at = NULL
                """,
                (username, password_hash, role, now, now),
            )
            conn.commit()
        return self.get_user(username) or {}

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, password_hash, role, created_at, updated_at, last_login_at, disabled_at
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        if not row:
            return None
        return {
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_login_at": row["last_login_at"],
            "disabled_at": row["disabled_at"],
        }

    def list_users(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT username FROM users"
        if not include_disabled:
            query += " WHERE disabled_at IS NULL"
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [record for row in rows if (record := self.get_user(row["username"])) is not None]

    def record_user_login(self, username: str) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET last_login_at = ?, updated_at = ?
                WHERE username = ?
                """,
                (now, now, username),
            )
            conn.commit()

    def create_session(
        self,
        *,
        session_id: str,
        token_hash: str,
        username: str,
        role: str,
        expires_at: float,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(
                    session_id, token_hash, username, role, metadata,
                    created_at, updated_at, last_seen_at, expires_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session_id,
                    token_hash,
                    username,
                    role,
                    _json_dumps(metadata or {}),
                    now,
                    now,
                    now,
                    expires_at,
                ),
            )
            conn.commit()
        return self.get_session(session_id) or {}

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "token_hash": row["token_hash"],
            "username": row["username"],
            "role": row["role"],
            "metadata": self._decode_json_row(row, "metadata"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_seen_at": row["last_seen_at"],
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
        }

    def touch_session(self, session_id: str) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET last_seen_at = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (now, now, session_id),
            )
            conn.commit()

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id
                FROM sessions
                WHERE token_hash = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        if not row:
            return None
        self.touch_session(row["session_id"])
        return self.get_session(row["session_id"])

    def revoke_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = ?, updated_at = ?
                WHERE session_id = ? AND revoked_at IS NULL
                """,
                (now, now, session_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_session(session_id)

    def revoke_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id
                FROM sessions
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (token_hash,),
            ).fetchone()
        if not row:
            return None
        return self.revoke_session(row["session_id"])

    def list_sessions(
        self,
        *,
        include_revoked: bool = False,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        self.delete_expired_sessions()
        query = "SELECT session_id FROM sessions WHERE expires_at > ?"
        params: list[Any] = [time.time()]
        if not include_revoked:
            query += " AND revoked_at IS NULL"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [record for row in rows if (record := self.get_session(row["session_id"])) is not None]

    def delete_expired_sessions(self) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM sessions
                WHERE expires_at <= ?
                """,
                (time.time(),),
            )
            conn.commit()
        return int(cursor.rowcount or 0)

    def create_service_account(
        self,
        account_id: str,
        name: str,
        role: str,
        scopes: List[str],
        token_hash: str,
        description: str = "",
        expires_at: float | None = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO service_accounts(
                    account_id, name, role, scopes, token_hash, description,
                    created_at, updated_at, expires_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    account_id,
                    name,
                    role,
                    _json_dumps({"items": scopes}),
                    token_hash,
                    str(description or "")[:500],
                    now,
                    now,
                    expires_at,
                ),
            )
            conn.commit()
        return self.get_service_account(account_id) or {}

    def get_service_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT account_id, name, role, scopes, description, created_at,
                       updated_at, expires_at, revoked_at
                FROM service_accounts
                WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()
        if not row:
            return None
        scopes_payload = self._decode_json_row(row, "scopes")
        return {
            "account_id": row["account_id"],
            "name": row["name"],
            "role": row["role"],
            "scopes": list(scopes_payload.get("items", [])),
            "description": row["description"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
        }

    def list_service_accounts(self, include_revoked: bool = True) -> List[Dict[str, Any]]:
        query = "SELECT account_id FROM service_accounts"
        if not include_revoked:
            query += " WHERE revoked_at IS NULL"
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [record for row in rows if (record := self.get_service_account(row["account_id"])) is not None]

    def get_service_account_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT account_id
                FROM service_accounts
                WHERE token_hash = ?
                  AND revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > ?)
                """,
                (token_hash, now),
            ).fetchone()
        if not row:
            return None
        return self.get_service_account(row["account_id"])

    def rotate_service_account(
        self,
        account_id: str,
        token_hash: str,
        expires_at: float | None = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE service_accounts
                SET token_hash = ?, updated_at = ?, expires_at = ?
                WHERE account_id = ? AND revoked_at IS NULL
                """,
                (token_hash, now, expires_at, account_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_service_account(account_id)

    def revoke_service_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE service_accounts
                SET revoked_at = ?, updated_at = ?
                WHERE account_id = ? AND revoked_at IS NULL
                """,
                (now, now, account_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_service_account(account_id)

    def create_job(
        self,
        job_id: str,
        operation_id: str,
        principal_type: str,
        principal_id: str,
        status: str,
        request_id: str,
        input_payload: Dict[str, Any],
        idempotency_key: str | None = None,
        approval_id: str | None = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_jobs(
                    job_id, operation_id, principal_type, principal_id, status,
                    request_id, idempotency_key, input_payload, result_payload,
                    error_payload, approval_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                """,
                (
                    job_id,
                    operation_id,
                    principal_type,
                    principal_id,
                    status,
                    request_id,
                    idempotency_key,
                    _json_dumps(input_payload),
                    approval_id,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_job(job_id) or {}

    def update_job(
        self,
        job_id: str,
        status: str,
        result_payload: Dict[str, Any] | None = None,
        error_payload: Dict[str, Any] | None = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE automation_jobs
                SET status = ?, result_payload = ?, error_payload = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    _json_dumps(result_payload) if result_payload is not None else None,
                    _json_dumps(error_payload) if error_payload is not None else None,
                    now,
                    job_id,
                ),
            )
            conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM automation_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "job_id": row["job_id"],
            "operation_id": row["operation_id"],
            "principal_type": row["principal_type"],
            "principal_id": row["principal_id"],
            "status": row["status"],
            "request_id": row["request_id"],
            "idempotency_key": row["idempotency_key"],
            "input": self._decode_json_row(row, "input_payload"),
            "result": self._decode_json_row(row, "result_payload") if row["result_payload"] else None,
            "error": self._decode_json_row(row, "error_payload") if row["error_payload"] else None,
            "approval_id": row["approval_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_jobs(
        self,
        limit: int = 100,
        principal_type: str | None = None,
        principal_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT job_id FROM automation_jobs"
        params: List[Any] = []
        if principal_type and principal_id:
            query += " WHERE principal_type = ? AND principal_id = ?"
            params.extend([principal_type, principal_id])
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [job for row in rows if (job := self.get_job(row["job_id"])) is not None]

    def create_approval(
        self,
        approval_id: str,
        operation_id: str,
        principal_type: str,
        principal_id: str,
        request_id: str,
        input_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_approvals(
                    approval_id, operation_id, principal_type, principal_id,
                    request_id, input_payload, status, decision_reason,
                    decided_by, job_id, created_at, updated_at, decided_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, ?, ?, NULL)
                """,
                (
                    approval_id,
                    operation_id,
                    principal_type,
                    principal_id,
                    request_id,
                    _json_dumps(input_payload),
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_approval(approval_id) or {}

    def get_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM automation_approvals
                WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "approval_id": row["approval_id"],
            "operation_id": row["operation_id"],
            "principal_type": row["principal_type"],
            "principal_id": row["principal_id"],
            "request_id": row["request_id"],
            "input": self._decode_json_row(row, "input_payload"),
            "status": row["status"],
            "decision_reason": row["decision_reason"],
            "decided_by": row["decided_by"],
            "job_id": row["job_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "decided_at": row["decided_at"],
        }

    def update_approval(
        self,
        approval_id: str,
        status: str,
        decision_reason: str = "",
        decided_by: str = "",
        job_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        decided_at = now if status in {"approved", "rejected"} else None
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE automation_approvals
                SET status = ?, decision_reason = ?, decided_by = ?, job_id = ?,
                    updated_at = ?, decided_at = ?
                WHERE approval_id = ?
                """,
                (
                    status,
                    str(decision_reason or "")[:500],
                    str(decided_by or "")[:120],
                    job_id,
                    now,
                    decided_at,
                    approval_id,
                ),
            )
            conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_approval(approval_id)

    def record_audit_event(
        self,
        audit_id: str,
        principal_type: str,
        principal_id: str,
        operation_id: str,
        request_id: str,
        idempotency_key: str | None,
        args_hash: str,
        outcome_status: str,
        approval_state: str | None,
        envelope: Dict[str, Any],
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events(
                    audit_id, principal_type, principal_id, operation_id,
                    request_id, idempotency_key, args_hash, outcome_status,
                    approval_state, envelope, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    principal_type,
                    principal_id,
                    operation_id,
                    request_id,
                    idempotency_key,
                    args_hash,
                    outcome_status,
                    approval_state,
                    _json_dumps(envelope),
                    time.time(),
                ),
            )
            conn.commit()

    def find_idempotent_envelope(
        self,
        principal_type: str,
        principal_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        record = self.find_idempotent_record(
            principal_type=principal_type,
            principal_id=principal_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )
        if not record:
            return None
        return record["envelope"]

    def find_idempotent_record(
        self,
        principal_type: str,
        principal_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT args_hash, envelope, outcome_status, approval_state
                FROM audit_events
                WHERE principal_type = ?
                  AND principal_id = ?
                  AND operation_id = ?
                  AND idempotency_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (principal_type, principal_id, operation_id, idempotency_key),
            ).fetchone()
        if not row:
            return None
        return {
            "args_hash": row["args_hash"],
            "envelope": json.loads(row["envelope"]),
            "outcome_status": row["outcome_status"],
            "approval_state": row["approval_state"],
        }
