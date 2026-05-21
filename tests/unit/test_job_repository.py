import datetime as dt

import pytest

from shared.db import connect, run_migrations
from shared.repositories.job_repository import (
    create_job,
    get_job,
    list_finished_before,
    set_error,
    update_status,
)


@pytest.fixture
def conn(tmp_db_path):
    c = connect(tmp_db_path)
    run_migrations(c)
    return c


def test_create_and_get(conn):
    create_job(conn, job_id="job-1", filename="a.mp3",
               hotwords_csv="x,y", hotword_group_ids_csv="1,2",
               output_format="json")
    job = get_job(conn, "job-1")
    assert job.id == "job-1"
    assert job.status == "queued"
    assert job.filename == "a.mp3"
    assert job.hotwords_csv == "x,y"
    assert job.output_format == "json"


def test_update_status_running_sets_started_at(conn):
    create_job(conn, job_id="j2")
    update_status(conn, "j2", "running")
    job = get_job(conn, "j2")
    assert job.status == "running"
    assert job.started_at is not None


def test_update_status_done_sets_finished_at(conn):
    create_job(conn, job_id="j3")
    update_status(conn, "j3", "running")
    update_status(conn, "j3", "done")
    job = get_job(conn, "j3")
    assert job.status == "done"
    assert job.finished_at is not None


def test_set_error_records_code_and_detail(conn):
    create_job(conn, job_id="j4")
    set_error(conn, "j4", code="DECODE_FAILED", detail="ffmpeg crashed")
    job = get_job(conn, "j4")
    assert job.status == "failed"
    assert job.error_code == "DECODE_FAILED"
    assert "ffmpeg" in job.error_detail


def test_get_nonexistent_returns_none(conn):
    assert get_job(conn, "nope") is None


def test_list_finished_before(conn):
    create_job(conn, job_id="old")
    update_status(conn, "old", "done")
    # backdate
    conn.execute("UPDATE jobs SET finished_at='2020-01-01T00:00:00Z' WHERE id='old'")
    conn.commit()

    create_job(conn, job_id="new")
    update_status(conn, "new", "done")

    cutoff = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    ids = list_finished_before(conn, cutoff)
    assert "old" in ids
    assert "new" not in ids
