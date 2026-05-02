from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from ..config import settings

_SCHEMA_LOCK = Lock()
_INITIALIZED_PATHS: set[str] = set()


def _db_path() -> str:
    return settings.HERMES_VOICE_DB_PATH


def _connect() -> sqlite3.Connection:
    ensure_schema()
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _utc_now_sql() -> str:
    return "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def ensure_schema() -> None:
    path = _db_path()
    if path in _INITIALIZED_PATHS:
        return
    with _SCHEMA_LOCK:
        if path in _INITIALIZED_PATHS:
            return
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS voice_sessions (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message_preview TEXT,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    hermes_conversation_id TEXT NOT NULL,
                    archived_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_voice_sessions_owner_updated
                    ON voice_sessions(owner_id, archived_at, updated_at DESC);

                CREATE TABLE IF NOT EXISTS voice_messages (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    turn_id TEXT,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    text TEXT NOT NULL,
                    final INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(session_id) REFERENCES voice_sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_voice_messages_session_created
                    ON voice_messages(owner_id, session_id, created_at ASC);
                """
            )
            conn.commit()
            _INITIALIZED_PATHS.add(path)
        finally:
            conn.close()


def reset_for_tests() -> None:
    with _SCHEMA_LOCK:
        _INITIALIZED_PATHS.clear()


def _session_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_message_preview": row["last_message_preview"],
        "message_count": row["message_count"],
        "conversation_id": row["hermes_conversation_id"],
        "hermes_conversation_id": row["hermes_conversation_id"],
        "archived_at": row["archived_at"],
    }


def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
    metadata: dict[str, Any]
    try:
        parsed = json.loads(row["metadata"])
        metadata = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        metadata = {}
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "turn_id": row["turn_id"],
        "role": row["role"],
        "text": row["text"],
        "final": bool(row["final"]),
        "created_at": row["created_at"],
        "metadata": metadata,
    }


def create_session(owner_id: str, title: str | None = None) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    with _connect() as conn:
        row = conn.execute(
            f"""
            INSERT INTO voice_sessions (
                id, owner_id, title, created_at, updated_at, hermes_conversation_id
            )
            VALUES (?, ?, ?, {_utc_now_sql()}, {_utc_now_sql()}, ?)
            RETURNING *
            """,
            (session_id, owner_id, title, session_id),
        ).fetchone()
        conn.commit()
    return _session_dict(row)


def list_sessions(owner_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    archived_clause = "" if include_archived else "AND archived_at IS NULL"
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM voice_sessions
            WHERE owner_id = ? {archived_clause}
            ORDER BY updated_at DESC, created_at DESC
            """,
            (owner_id,),
        ).fetchall()
    return [_session_dict(row) for row in rows]


def session_exists(session_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM voice_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return row is not None


def get_session(
    owner_id: str,
    session_id: str,
    *,
    include_archived: bool = True,
) -> dict[str, Any] | None:
    archived_clause = "" if include_archived else "AND archived_at IS NULL"
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT * FROM voice_sessions
            WHERE owner_id = ? AND id = ? {archived_clause}
            """,
            (owner_id, session_id),
        ).fetchone()
    return _session_dict(row) if row is not None else None


def patch_session(
    owner_id: str,
    session_id: str,
    *,
    title: str | None | object = ...,
    archived: bool | None = None,
) -> dict[str, Any] | None:
    assignments: list[str] = [f"updated_at = {_utc_now_sql()}"]
    params: list[Any] = []
    if title is not ...:
        assignments.append("title = ?")
        params.append(title)
    if archived is True:
        assignments.append(f"archived_at = COALESCE(archived_at, {_utc_now_sql()})")
    elif archived is False:
        assignments.append("archived_at = NULL")

    params.extend([owner_id, session_id])
    with _connect() as conn:
        row = conn.execute(
            f"""
            UPDATE voice_sessions
            SET {", ".join(assignments)}
            WHERE owner_id = ? AND id = ?
            RETURNING *
            """,
            params,
        ).fetchone()
        conn.commit()
    return _session_dict(row) if row is not None else None


def archive_session(owner_id: str, session_id: str) -> dict[str, Any] | None:
    return patch_session(owner_id, session_id, archived=True)


def add_message(
    owner_id: str,
    session_id: str,
    *,
    turn_id: str | None,
    role: str,
    text: str,
    final: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    preview = text.strip().replace("\n", " ")[:240] or None
    metadata_json = json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True)
    with _connect() as conn:
        row = conn.execute(
            f"""
            INSERT INTO voice_messages (
                id, owner_id, session_id, turn_id, role, text, final, created_at, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, {_utc_now_sql()}, ?)
            RETURNING *
            """,
            (message_id, owner_id, session_id, turn_id, role, text, int(final), metadata_json),
        ).fetchone()
        conn.execute(
            f"""
            UPDATE voice_sessions
            SET updated_at = {_utc_now_sql()},
                last_message_preview = COALESCE(?, last_message_preview),
                message_count = message_count + 1
            WHERE owner_id = ? AND id = ?
            """,
            (preview, owner_id, session_id),
        )
        conn.commit()
    return _message_dict(row)


def list_messages(owner_id: str, session_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM voice_messages
            WHERE owner_id = ? AND session_id = ?
            ORDER BY created_at ASC
            """,
            (owner_id, session_id),
        ).fetchall()
    return [_message_dict(row) for row in rows]
