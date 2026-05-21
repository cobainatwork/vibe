"""Retention cleanup script.

Deletes old result directories and job rows per configured retention policy.

Run inside the container:
    python /app/scripts/retention_cleanup.py

The editable install (uv pip install -e .) inside the container makes
`from shared.*` imports work without any sys.path tricks.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
import sys
from pathlib import Path

from shared.config import load_config
from shared.db import connect, run_migrations

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","service":"retention","msg":%(message)r}',
)
log = logging.getLogger(__name__)


def cleanup_results(result_dir: Path, conn, cutoff: dt.datetime) -> int:
    """Delete result_dir/<job_id>/ where job.finished_at < cutoff.

    Orphan directories (no matching DB row) are left untouched because
    without a finished_at timestamp we cannot determine their age safely.

    Returns the count of directories actually removed.
    """
    deleted = 0
    cutoff_iso = cutoff.isoformat()

    for job_dir in sorted(result_dir.iterdir()):
        if not job_dir.is_dir():
            continue
        job_id = job_dir.name
        row = conn.execute(
            "SELECT finished_at FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            # Orphan — no DB record, cannot determine age; skip.
            log.info(
                json.dumps({"event": "retention_skip_orphan", "job_id": job_id})
            )
            continue
        finished_at = row["finished_at"]
        if finished_at is None:
            # Job is not finished yet; skip.
            continue
        if finished_at < cutoff_iso:
            log.info(
                json.dumps({
                    "event": "retention_delete_result_dir",
                    "job_id": job_id,
                    "finished_at": finished_at,
                })
            )
            shutil.rmtree(job_dir)
            deleted += 1

    return deleted


def cleanup_jobs_table(conn, cutoff: dt.datetime) -> int:
    """DELETE FROM jobs WHERE finished_at < cutoff. Returns rowcount."""
    cutoff_iso = cutoff.isoformat()
    cur = conn.execute(
        "DELETE FROM jobs WHERE finished_at < ?", (cutoff_iso,)
    )
    conn.commit()
    deleted = cur.rowcount
    log.info(
        json.dumps({"event": "retention_delete_job_rows", "deleted_rows": deleted})
    )
    return deleted


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    run_migrations(conn)

    now = dt.datetime.now(dt.timezone.utc)
    result_cutoff = now - dt.timedelta(days=cfg.retain_result_days)
    job_cutoff = now - dt.timedelta(days=cfg.retain_job_record_days)

    n_results = cleanup_results(cfg.result_dir, conn, result_cutoff)
    n_jobs = cleanup_jobs_table(conn, job_cutoff)

    log.info(
        json.dumps({
            "event": "retention_cleanup",
            "deleted_result_dirs": n_results,
            "deleted_job_rows": n_jobs,
        })
    )
    print(f"Deleted {n_results} result dirs, {n_jobs} job rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
