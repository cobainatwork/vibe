import sqlite3

from shared.db import connect, run_migrations


def test_migrations_create_tables(tmp_db_path):
    conn = connect(tmp_db_path)
    run_migrations(conn)

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor]
    assert "jobs" in tables
    assert "hotword_groups" in tables


def test_jobs_schema_columns(tmp_db_path):
    conn = connect(tmp_db_path)
    run_migrations(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)")]
    expected = {
        "id", "status", "filename", "audio_duration_sec",
        "hotwords_csv", "hotword_group_ids_csv", "output_format",
        "result_path", "raw_text_path", "error_code", "error_detail",
        "created_at", "started_at", "finished_at",
    }
    assert expected.issubset(set(cols))


def test_hotword_groups_schema(tmp_db_path):
    conn = connect(tmp_db_path)
    run_migrations(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(hotword_groups)")]
    assert {"id", "name", "words_csv", "created_at", "updated_at"} <= set(cols)


def test_migrations_idempotent(tmp_db_path):
    conn = connect(tmp_db_path)
    run_migrations(conn)
    run_migrations(conn)  # should not fail
    count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    assert count >= 2
