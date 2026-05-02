"""Persistence layer: Convex adapter bridge with SQLite fallback/cache."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from src.app.redaction import redact_text, redact_value


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(redact_value(payload), ensure_ascii=True, sort_keys=True)


@dataclass
class SyncResult:
    attempted: int = 0
    synced: int = 0
    failed: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class ConvexAdapterClient:
    """HTTP client for the hybrid Node/TypeScript Convex adapter with circuit breaker."""

    def __init__(
        self, base_url: str = "", api_key: str = "", timeout_seconds: float = 3.0
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = api_key or ""
        self.timeout_seconds = timeout_seconds
        self._cb_failures = 0
        self._cb_last_failure = 0.0
        self._cb_open_until = 0.0
        self._cb_successes = 0
        self.CB_THRESHOLD = 5
        self.CB_RESET_SECONDS = 30.0
        self.CB_HALF_OPEN_MAX = 1

    @property
    def circuit_open(self) -> bool:
        if self._cb_failures < self.CB_THRESHOLD:
            return False
        if time.time() < self._cb_open_until:
            return True
        return False

    def _record_success(self) -> None:
        self._cb_successes += 1
        if self._cb_failures >= self.CB_THRESHOLD:
            self._cb_failures = 0
            self._cb_open_until = 0.0

    def _record_failure(self) -> None:
        self._cb_failures += 1
        self._cb_last_failure = time.time()
        if self._cb_failures >= self.CB_THRESHOLD:
            self._cb_open_until = time.time() + self.CB_RESET_SECONDS

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and requests is not None)

    @property
    def circuit_state(self) -> str:
        if self._cb_failures < self.CB_THRESHOLD:
            return "closed"
        if time.time() < self._cb_open_until:
            return "open"
        return "half-open"

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Adapter-Key"] = self.api_key
        return headers

    def health(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        if self.circuit_open:
            return {"ok": False, "reason": f"circuit_{self.circuit_state}"}
        try:
            resp = requests.get(
                f"{self.base_url}/sync/health",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            self._record_success()
            return {"ok": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as exc:
            self._record_failure()
            return {"ok": False, "reason": str(exc)}

    def push_event(
        self, event_id: str, entity_type: str, payload: Dict[str, Any]
    ) -> bool:
        if not self.enabled:
            return False
        if self.circuit_open:
            return False
        body = {
            "eventId": event_id,
            "entityType": entity_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        try:
            resp = requests.post(
                f"{self.base_url}/sync/event",
                data=_json_dumps(body),
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            ok = resp.status_code in (200, 201, 202)
            if ok:
                self._record_success()
            else:
                self._record_failure()
            return ok
        except Exception:
            self._record_failure()
            return False

    def fetch_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        if self.circuit_open:
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/data/traces?limit={limit}",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            if resp.status_code != 200:
                self._record_failure()
                return []
            data = resp.json()
            traces = data.get("traces", [])
            self._record_success()
            return traces if isinstance(traces, list) else []
        except Exception:
            self._record_failure()
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/data/traces?limit={limit}",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            traces = data.get("traces", [])
            return traces if isinstance(traces, list) else []
        except Exception:  # pragma: no cover
            return []


class SQLiteStore:
    """Canonical local persistence and sync queue."""

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
                CREATE TABLE IF NOT EXISTS traces (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS costs (
                    conversation_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_events (
                    event_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_turns_conversation_created
                ON conversation_turns(conversation_id, created_at);
                """
            )
            conn.commit()

    @staticmethod
    def _feedback_id(payload: Dict[str, Any]) -> str:
        raw = (
            f"{payload.get('conversation_id', '')}:"
            f"{payload.get('rating', '')}:"
            f"{payload.get('timestamp', '')}:"
            f"{payload.get('feedback_text', '')}"
        )
        return sha256(raw.encode()).hexdigest()[:20]

    def upsert_trace(self, trace_payload: Dict[str, Any]) -> None:
        sanitized = redact_value(trace_payload)
        session_id = str(sanitized.get("session_id") or "")
        if not session_id:
            return
        now = time.time()
        payload = _json_dumps(sanitized)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traces(session_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (session_id, payload, now),
            )
            conn.commit()

    def get_trace(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM traces WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["payload"])

    def list_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM traces ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def append_feedback(self, feedback_payload: Dict[str, Any]) -> str:
        feedback_id = feedback_payload.get("feedback_id") or self._feedback_id(
            feedback_payload
        )
        payload = redact_value(dict(feedback_payload))
        payload["feedback_id"] = feedback_id
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback(feedback_id, conversation_id, payload, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(feedback_id)
                DO UPDATE SET payload=excluded.payload, created_at=excluded.created_at
                """,
                (
                    feedback_id,
                    payload.get("conversation_id", "unknown"),
                    _json_dumps(payload),
                    now,
                ),
            )
            conn.commit()
        return feedback_id

    def list_feedback(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM feedback ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def upsert_cost(self, conversation_id: str, cost_payload: Dict[str, Any]) -> None:
        if not conversation_id:
            return
        now = time.time()
        sanitized = redact_value(cost_payload)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO costs(conversation_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id)
                DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (conversation_id, _json_dumps(sanitized), now),
            )
            conn.commit()

    def upsert_conversation(
        self,
        conversation_id: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not conversation_id:
            return
        payload = redact_value(metadata or {})
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations(conversation_id, user_id, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id)
                DO UPDATE SET user_id=excluded.user_id, metadata=excluded.metadata, updated_at=excluded.updated_at
                """,
                (
                    conversation_id,
                    redact_text(user_id or "anonymous"),
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )
            conn.commit()

    def save_conversation(
        self, conversation_id: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.upsert_conversation(conversation_id, user_id, metadata or {})

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT conversation_id, user_id, metadata, created_at, updated_at
                FROM conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "conversation_id": row["conversation_id"],
            "user_id": row["user_id"],
            "metadata": json.loads(row["metadata"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def add_conversation_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = time.time()
        sanitized_metadata = redact_value(metadata or {})
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversation_turns(conversation_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    role,
                    redact_text(content),
                    _json_dumps(sanitized_metadata),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE conversation_id = ?
                """,
                (now, conversation_id),
            )
            conn.commit()
        return int(cursor.lastrowid)

    def save_conversation_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return self.add_conversation_turn(conversation_id, role, content, metadata or {})

    def list_conversation_turns(
        self, conversation_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT turn_id, role, content, metadata, created_at
                FROM conversation_turns
                WHERE conversation_id = ?
                ORDER BY created_at ASC, turn_id ASC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        turns: List[Dict[str, Any]] = []
        for row in rows:
            turns.append(
                {
                    "turn_id": int(row["turn_id"]),
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]),
                    "created_at": row["created_at"],
                }
            )
        return turns

    def get_costs(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM costs").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def enqueue_sync_event(
        self, event_id: str, entity_type: str, payload: Dict[str, Any]
    ) -> None:
        now = time.time()
        sanitized = redact_value(payload)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_events(event_id, entity_type, payload, synced, attempts, updated_at)
                VALUES (?, ?, ?, 0, 0, ?)
                ON CONFLICT(event_id)
                DO UPDATE SET payload=excluded.payload, synced=0, updated_at=excluded.updated_at
                """,
                (event_id, entity_type, _json_dumps(sanitized), now),
            )
            conn.commit()

    def pending_sync_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, entity_type, payload, attempts
                FROM sync_events
                WHERE synced = 0
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        events = []
        for row in rows:
            events.append(
                {
                    "event_id": row["event_id"],
                    "entity_type": row["entity_type"],
                    "payload": json.loads(row["payload"]),
                    "attempts": row["attempts"],
                }
            )
        return events

    def mark_synced(self, event_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE sync_events SET synced = 1, attempts = attempts + 1, last_error = NULL, updated_at = ? WHERE event_id = ?",
                (time.time(), event_id),
            )
            conn.commit()

    def mark_sync_failed(self, event_id: str, error: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE sync_events SET attempts = attempts + 1, last_error = ?, updated_at = ? WHERE event_id = ?",
                (redact_text(error)[:500], time.time(), event_id),
            )
            conn.commit()

    def prune_retention(
        self,
        *,
        trace_retention_days: int,
        feedback_retention_days: int,
    ) -> Dict[str, int]:
        deleted = {"traces": 0, "feedback": 0, "sync_events": 0}
        now = time.time()
        with self._lock, self._connect() as conn:
            if trace_retention_days > 0:
                trace_cutoff = now - (trace_retention_days * 24 * 60 * 60)
                cursor = conn.execute(
                    "DELETE FROM traces WHERE updated_at <= ?",
                    (trace_cutoff,),
                )
                deleted["traces"] = int(cursor.rowcount or 0)
            if feedback_retention_days > 0:
                feedback_cutoff = now - (feedback_retention_days * 24 * 60 * 60)
                cursor = conn.execute(
                    "DELETE FROM feedback WHERE created_at <= ?",
                    (feedback_cutoff,),
                )
                deleted["feedback"] = int(cursor.rowcount or 0)
            sync_cutoff = now - (30 * 24 * 60 * 60)
            cursor = conn.execute(
                """
                DELETE FROM sync_events
                WHERE synced = 1 AND updated_at <= ?
                """,
                (sync_cutoff,),
            )
            deleted["sync_events"] = int(cursor.rowcount or 0)
            conn.commit()
        return deleted

    def stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            traces = conn.execute("SELECT COUNT(*) AS c FROM traces").fetchone()["c"]
            feedback = conn.execute("SELECT COUNT(*) AS c FROM feedback").fetchone()[
                "c"
            ]
            costs = conn.execute("SELECT COUNT(*) AS c FROM costs").fetchone()["c"]
            conversations = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations"
            ).fetchone()["c"]
            turns = conn.execute(
                "SELECT COUNT(*) AS c FROM conversation_turns"
            ).fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM sync_events WHERE synced = 0"
            ).fetchone()["c"]
        return {
            "traces": int(traces),
            "feedback": int(feedback),
            "costs": int(costs),
            "conversations": int(conversations),
            "conversation_turns": int(turns),
            "pending_sync": int(pending),
            "sqlite_path": self.sqlite_path,
        }


class HybridStore:
    """Convex-primary sync profile with deterministic SQLite fallback."""

    def __init__(
        self,
        sqlite_path: str,
        convex_adapter_url: str = "",
        convex_api_key: str = "",
    ):
        self.sqlite = SQLiteStore(sqlite_path)
        self.convex = ConvexAdapterClient(convex_adapter_url, convex_api_key)

    @staticmethod
    def _event_id(prefix: str, stable_value: str) -> str:
        digest = sha256(f"{prefix}:{stable_value}".encode()).hexdigest()[:24]
        return f"{prefix}:{digest}"

    def save_trace(self, trace_payload: Dict[str, Any]) -> None:
        self.sqlite.upsert_trace(trace_payload)
        sid = str(trace_payload.get("session_id", "unknown"))
        event_id = self._event_id("trace", sid)
        self.sqlite.enqueue_sync_event(event_id, "trace", trace_payload)

    def get_trace(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sqlite.get_trace(session_id)

    def list_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.convex.enabled:
            remote = self.convex.fetch_traces(limit=limit)
            if remote:
                return remote
        return self.sqlite.list_traces(limit=limit)

    def save_feedback(self, feedback_payload: Dict[str, Any]) -> str:
        fid = self.sqlite.append_feedback(feedback_payload)
        event_id = self._event_id("feedback", fid)
        self.sqlite.enqueue_sync_event(event_id, "feedback", feedback_payload)
        return fid

    def list_feedback(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.sqlite.list_feedback(limit=limit)

    def save_cost(self, conversation_id: str, cost_payload: Dict[str, Any]) -> None:
        self.sqlite.upsert_cost(conversation_id, cost_payload)
        event_id = self._event_id("cost", conversation_id)
        self.sqlite.enqueue_sync_event(event_id, "cost", cost_payload)

    def list_costs(self) -> List[Dict[str, Any]]:
        return self.sqlite.get_costs()

    def save_conversation(
        self, conversation_id: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.sqlite.upsert_conversation(conversation_id, user_id, metadata or {})

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self.sqlite.get_conversation(conversation_id)

    def save_conversation_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return self.sqlite.add_conversation_turn(
            conversation_id, role, content, metadata or {}
        )

    def list_conversation_turns(
        self, conversation_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self.sqlite.list_conversation_turns(conversation_id, limit=limit)

    def prune_retention(
        self,
        *,
        trace_retention_days: int,
        feedback_retention_days: int,
    ) -> Dict[str, int]:
        return self.sqlite.prune_retention(
            trace_retention_days=trace_retention_days,
            feedback_retention_days=feedback_retention_days,
        )

    def sync(self, limit: int = 100) -> SyncResult:
        result = SyncResult()
        pending = self.sqlite.pending_sync_events(limit=limit)
        result.attempted = len(pending)
        if not pending:
            return result

        for event in pending:
            event_id = event["event_id"]
            try:
                ok = self.convex.push_event(
                    event_id=event_id,
                    entity_type=event["entity_type"],
                    payload=event["payload"],
                )
                if ok:
                    self.sqlite.mark_synced(event_id)
                    result.synced += 1
                else:
                    self.sqlite.mark_sync_failed(event_id, "adapter_rejected")
                    result.failed += 1
                    result.errors.append(f"{event_id}: adapter_rejected")
            except Exception as exc:  # pragma: no cover
                self.sqlite.mark_sync_failed(event_id, str(exc))
                result.failed += 1
                result.errors.append(f"{event_id}: {exc}")

        return result

    def stats(self) -> Dict[str, Any]:
        stats = self.sqlite.stats()
        stats["convex_enabled"] = self.convex.enabled
        return stats


def import_legacy_json(
    store: HybridStore,
    traces_dir: str,
    feedback_dir: str,
    costs_dir: str,
) -> Dict[str, int]:
    """Import legacy JSON and JSONL records into canonical store."""

    imported = {"traces": 0, "feedback": 0, "costs": 0}

    traces_path = Path(traces_dir)
    if traces_path.exists():
        for path in traces_path.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("session_id"):
                    store.save_trace(payload)
                    imported["traces"] += 1
            except Exception:
                continue

    feedback_path = Path(feedback_dir)
    if feedback_path.exists():
        for path in feedback_path.glob("*.jsonl"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        payload = json.loads(line)
                        if payload.get("id") and not payload.get("feedback_id"):
                            payload["feedback_id"] = str(payload["id"])
                        store.save_feedback(payload)
                        imported["feedback"] += 1
            except Exception:
                continue

    costs_path = Path(costs_dir)
    if costs_path.exists():
        for path in costs_path.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                cid = str(payload.get("conversation_id") or path.stem)
                if cid:
                    store.save_cost(cid, payload)
                    imported["costs"] += 1
            except Exception:
                continue

    return imported
