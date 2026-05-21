"""CRUD for jobs table."""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    status: str
    filename: str | None
    audio_duration_sec: float | None
    hotwords_csv: str | None
    hotword_group_ids_csv: str | None
    output_format: str
    result_path: str | None
    raw_text_path: str | None
    error_code: str | None
    error_detail: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Job":
        return cls(**{k: row[k] for k in row.keys()})


def create_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    filename: str | None = None,
    hotwords_csv: str | None = None,
    hotword_group_ids_csv: str | None = None,
    output_format: str = "json",
) -> None:
    conn.execute(
        """
        INSERT INTO jobs (id, status, filename, hotwords_csv,
                          hotword_group_ids_csv, output_format, created_at)
        VALUES (?, 'queued', ?, ?, ?, ?, ?)
        """,
        (job_id, filename, hotwords_csv, hotword_group_ids_csv,
         output_format, _now()),
    )
    conn.commit()


def update_status(conn: sqlite3.Connection, job_id: str, status: str) -> None:
    now = _now()
    if status == "running":
        conn.execute("UPDATE jobs SET status=?, started_at=? WHERE id=?",
                     (status, now, job_id))
    elif status in ("done", "failed", "aborted"):
        conn.execute("UPDATE jobs SET status=?, finished_at=? WHERE id=?",
                     (status, now, job_id))
    else:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    conn.commit()


def set_audio_duration(conn: sqlite3.Connection, job_id: str, seconds: float) -> None:
    conn.execute("UPDATE jobs SET audio_duration_sec=? WHERE id=?",
                 (seconds, job_id))
    conn.commit()


def set_result_path(conn: sqlite3.Connection, job_id: str,
                    result_path: str, raw_text_path: str | None = None) -> None:
    conn.execute(
        "UPDATE jobs SET result_path=?, raw_text_path=? WHERE id=?",
        (result_path, raw_text_path, job_id),
    )
    conn.commit()


def set_error(conn: sqlite3.Connection, job_id: str,
              *, code: str, detail: str) -> None:
    conn.execute(
        "UPDATE jobs SET status='failed', error_code=?, error_detail=?, finished_at=? WHERE id=?",
        (code, detail, _now(), job_id),
    )
    conn.commit()


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return Job.from_row(row) if row else None


def list_finished_before(conn: sqlite3.Connection, cutoff: dt.datetime) -> list[str]:
    cutoff_iso = cutoff.isoformat()
    rows = conn.execute(
        "SELECT id FROM jobs WHERE finished_at < ?",
        (cutoff_iso,),
    ).fetchall()
    return [r["id"] for r in rows]
