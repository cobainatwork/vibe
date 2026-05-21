import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    keys = tmp_path / "k.yaml"
    keys.write_text("- {name: t, key: t-key}\n")
    monkeypatch.setenv("API_KEYS_PATH", str(keys))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "u"))
    monkeypatch.setenv("RESULT_DIR", str(tmp_path / "r"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    from gateway.main import create_app
    app = create_app()
    return TestClient(app), app, tmp_path


HDR = {"X-API-Key": "t-key"}


def test_result_not_found_404(client):
    c, _, _ = client
    r = c.get("/v1/jobs/nonexistent/result", headers=HDR)
    assert r.status_code == 404


def test_result_json(client):
    c, app, tmp_path = client
    # seed
    from shared.repositories.job_repository import create_job, set_result_path, update_status
    conn = app.state.db
    create_job(conn, job_id="jx", filename="a.mp3", output_format="json")
    update_status(conn, "jx", "running")
    update_status(conn, "jx", "done")

    out_dir = tmp_path / "r" / "jx"
    out_dir.mkdir(parents=True)
    (out_dir / "output.json").write_text(json.dumps({"segments": [{"text": "ok"}]}))
    set_result_path(conn, "jx", str(out_dir / "output.json"))

    r = c.get("/v1/jobs/jx/result", headers=HDR)
    assert r.status_code == 200
    assert r.json()["segments"][0]["text"] == "ok"


def test_result_srt_content_type(client):
    c, app, tmp_path = client
    from shared.repositories.job_repository import create_job, set_result_path, update_status
    conn = app.state.db
    create_job(conn, job_id="js", filename="a.mp3", output_format="srt")
    update_status(conn, "js", "running")
    update_status(conn, "js", "done")
    out_dir = tmp_path / "r" / "js"
    out_dir.mkdir(parents=True)
    (out_dir / "output.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n[Speaker 0] hi\n")
    set_result_path(conn, "js", str(out_dir / "output.json"))  # always points to json
    # request srt
    r = c.get("/v1/jobs/js/result?format=srt", headers=HDR)
    assert r.status_code == 200
    assert "text/" in r.headers["content-type"]
