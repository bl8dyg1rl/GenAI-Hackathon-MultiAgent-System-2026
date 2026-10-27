"""SQLite event store shared by the agents (World-Model-inspired event log).

This is a small application-local shared workspace, not a claim of official
Meterless World Model conformance. It records every agent hand-off and model call.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "data/agent_runs.sqlite3"
_LOCK = threading.RLock()


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: Any) -> Any:
    """Redact fields and common credential patterns before writing local logs."""
    if isinstance(value, dict):
        safe = {}
        for key, child in value.items():
            key_lower = str(key).casefold()
            if any(part in key_lower for part in ("token", "authorization", "password", "api_key", "secret", "credential")):
                safe[key] = "[REDACTED]" if child else child
            else:
                safe[key] = _redact(child)
        return safe
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
        value = re.sub(r"\b(?:sk-[A-Za-z0-9]{16,}|rt-[A-Za-z0-9_-]{8,})\b", "[REDACTED]", value)
        return value
    return value


def _json(value: Any) -> str:
    return json.dumps(_redact(value), ensure_ascii=False, separators=(",", ":"), default=str)


class StateStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("AGENT_DB_PATH", DEFAULT_DB_PATH)
        path = Path(self.db_path)
        if self.db_path != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    @contextmanager
    def _db(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialise(self) -> None:
        with _LOCK, self._db() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    question TEXT NOT NULL,
                    intent TEXT,
                    confidence REAL,
                    answer TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    success INTEGER,
                    duration_ms INTEGER,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, id);
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    delivered_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_messages_inbox ON agent_messages(run_id, recipient, delivered_at, id);
                """
            )

    def create_run(self, run_id: str, trace_id: str, question: str, intent: str, confidence: float) -> None:
        with _LOCK, self._db() as db:
            db.execute(
                "INSERT INTO runs(run_id, trace_id, created_at, status, question, intent, confidence) VALUES(?,?,?,?,?,?,?)",
                (run_id, trace_id, utc_iso(), "running", question, intent, float(confidence)),
            )

    def finish_run(self, run_id: str, *, status: str, answer: str, summary: dict[str, Any]) -> None:
        with _LOCK, self._db() as db:
            db.execute(
                "UPDATE runs SET finished_at=?, status=?, answer=?, summary_json=? WHERE run_id=?",
                (utc_iso(), status, answer, _json(summary), run_id),
            )

    def log_event(self, run_id: str, agent: str, event_type: str, summary: str,
                  payload: Any = None, *, success: bool | None = None, duration_ms: int | None = None) -> int:
        success_int = None if success is None else (1 if success else 0)
        with _LOCK, self._db() as db:
            cursor = db.execute(
                "INSERT INTO agent_events(run_id,created_at,agent,event_type,summary,success,duration_ms,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, utc_iso(), agent, event_type, summary[:500], success_int,
                 duration_ms, _json(payload or {})),
            )
            return int(cursor.lastrowid)

    def send_message(self, run_id: str, sender: str, recipient: str, message_type: str,
                     payload: dict[str, Any]) -> int:
        with _LOCK, self._db() as db:
            cursor = db.execute(
                "INSERT INTO agent_messages(run_id,created_at,sender,recipient,message_type,payload_json) VALUES(?,?,?,?,?,?)",
                (run_id, utc_iso(), sender, recipient, message_type, _json(payload)),
            )
            message_id = int(cursor.lastrowid)
            db.execute(
                "INSERT INTO agent_events(run_id,created_at,agent,event_type,summary,success,payload_json) VALUES(?,?,?,?,?,?,?)",
                (run_id, utc_iso(), sender, "agent.message.sent", f"Mensaje #{message_id} enviado a {recipient}: {message_type}", 1,
                 _json({"message_id": message_id, "recipient": recipient, "message_type": message_type, "payload": payload})),
            )
            return message_id

    def receive_messages(self, run_id: str, recipient: str) -> list[dict[str, Any]]:
        with _LOCK, self._db() as db:
            rows = db.execute(
                "SELECT * FROM agent_messages WHERE run_id=? AND recipient=? AND delivered_at IS NULL ORDER BY id",
                (run_id, recipient),
            ).fetchall()
            if not rows:
                return []
            now = utc_iso()
            ids = [int(row["id"]) for row in rows]
            db.executemany("UPDATE agent_messages SET delivered_at=? WHERE id=?", [(now, i) for i in ids])
            for row in rows:
                db.execute(
                    "INSERT INTO agent_events(run_id,created_at,agent,event_type,summary,success,payload_json) VALUES(?,?,?,?,?,?,?)",
                    (run_id, now, recipient, "agent.message.received",
                     f"Mensaje #{row['id']} recibido de {row['sender']}: {row['message_type']}", 1,
                     _json({"message_id": row["id"], "sender": row["sender"],
                            "message_type": row["message_type"], "payload": json.loads(row["payload_json"])})),
                )
            return [{"id": int(row["id"]), "sender": row["sender"], "message_type": row["message_type"],
                     "payload": json.loads(row["payload_json"])} for row in rows]

    def list_events(self, run_id: str, *, limit: int = 300) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM agent_events WHERE run_id=? ORDER BY id LIMIT ?", (run_id, min(max(limit, 1), 1000))
            ).fetchall()
        return [{
            "id": row["id"], "created_at": row["created_at"], "agent": row["agent"],
            "event_type": row["event_type"], "summary": row["summary"],
            "success": None if row["success"] is None else bool(row["success"]),
            "duration_ms": row["duration_ms"], "payload": json.loads(row["payload_json"]),
        } for row in rows]

    def list_messages(self, run_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM agent_messages WHERE run_id=? ORDER BY id LIMIT ?", (run_id, min(max(limit, 1), 1000))
            ).fetchall()
        return [{"id": row["id"], "created_at": row["created_at"], "sender": row["sender"],
                 "recipient": row["recipient"], "message_type": row["message_type"],
                 "payload": json.loads(row["payload_json"]), "delivered": bool(row["delivered_at"])} for row in rows]

    def recent_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT run_id,trace_id,created_at,finished_at,status,question,intent,confidence,answer FROM runs ORDER BY created_at DESC LIMIT ?",
                              (min(max(limit, 1), 100),)).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["summary"] = json.loads(result.pop("summary_json"))
        return result
