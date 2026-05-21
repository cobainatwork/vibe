"""Unit tests for scripts/retention_cleanup.py."""
import datetime as dt
import sys
from pathlib import Path

# Make scripts/ importable for tests running from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from retention_cleanup import cleanup_jobs_table, cleanup_results  # noqa: E402

from shared.db import connect, run_migrations  # noqa: E402
from shared.repositories.job_repository import (  # noqa: E402
    create_job,
    get_job,
    update_status,
)


def test_cleanup_removes_old_results_keeps_recent(tmp_path):
    conn = connect(tmp_path / "test.db")
    run_migrations(conn)
    result_dir = tmp_path / "results"
    result_dir.mkdir()

    # Old job (will be cleaned)
    create_job(conn, job_id="old", filename="a.mp3")
    update_status(conn, "old", "running")
    update_status(conn, "old", "done")
    conn.execute(
        "UPDATE jobs SET finished_at='2020-01-01T00:00:00+00:00' WHERE id='old'"
    )
    conn.commit()
    (result_dir / "old").mkdir()
    (result_dir / "old" / "output.json").write_text("{}")

    # Recent job (kept)
    create_job(conn, job_id="new", filename="b.mp3")
    update_status(conn, "new", "running")
    update_status(conn, "new", "done")
    (result_dir / "new").mkdir()
    (result_dir / "new" / "output.json").write_text("{}")

    cutoff = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    n = cleanup_results(result_dir, conn, cutoff)
    assert n == 1
    assert not (result_dir / "old").exists()
    assert (result_dir / "new").exists()


def test_cleanup_removes_old_job_rows(tmp_path):
    conn = connect(tmp_path / "test.db")
    run_migrations(conn)

    create_job(conn, job_id="old", filename="a.mp3")
    update_status(conn, "old", "running")
    update_status(conn, "old", "done")
    conn.execute(
        "UPDATE jobs SET finished_at='2020-01-01T00:00:00+00:00' WHERE id='old'"
    )
    conn.commit()

    create_job(conn, job_id="new", filename="b.mp3")
    update_status(conn, "new", "running")
    update_status(conn, "new", "done")

    cutoff = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    n = cleanup_jobs_table(conn, cutoff)
    assert n == 1
    assert get_job(conn, "old") is None
    assert get_job(conn, "new") is not None


def test_cleanup_orphan_result_dir_no_db_row(tmp_path):
    # Edge case: directory exists but no jobs row — should NOT delete
    # (we use finished_at to decide; absent row means we can't know its age)
    conn = connect(tmp_path / "test.db")
    run_migrations(conn)
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "orphan").mkdir()
    cutoff = dt.datetime.now(dt.timezone.utc)
    n = cleanup_results(result_dir, conn, cutoff)
    # Orphan is skipped (not deleted), count is 0, and no crash.
    assert n == 0
    assert (result_dir / "orphan").exists()
