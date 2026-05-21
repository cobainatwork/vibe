"""SQLite connection + simple migrations.

We use raw sqlite3 (stdlib) to keep deps minimal.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path


def utc_now_iso() -> str:
    """Current UTC time in ISO 8601 format."""
    return dt.datetime.now(dt.timezone.utc).isoformat()


TRANSCRIBE_QUEUE_NAME = "transcribe"
TRANSCRIBE_QUEUE_REDIS_KEY = f"rq:queue:{TRANSCRIBE_QUEUE_NAME}"

SCHEMA_V1 = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        filename TEXT,
        audio_duration_sec REAL,
        hotwords_csv TEXT,
        hotword_group_ids_csv TEXT,
        output_format TEXT NOT NULL DEFAULT 'json',
        result_path TEXT,
        raw_text_path TEXT,
        error_code TEXT,
        error_detail TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_jobs_finished_at ON jobs(finished_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS hotword_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        words_csv TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
]


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection with sensible defaults."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply migrations idempotently."""
    for stmt in SCHEMA_V1:
        conn.execute(stmt)
    conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")
    conn.commit()
