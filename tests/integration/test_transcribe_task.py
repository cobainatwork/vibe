import json
import subprocess
import threading
import time
from pathlib import Path

import pytest
import redis
import uvicorn

from shared.config import load_config
from shared.db import connect, run_migrations
from shared.repositories.job_repository import create_job, get_job
from worker.tasks.transcribe import transcribe_job


@pytest.fixture(scope="module")
def fake_vllm_url():
    from tests.fixtures.fake_vllm import app
    config = uvicorn.Config(app, host="127.0.0.1", port=8012, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        try:
            import httpx
            httpx.get("http://127.0.0.1:8012/v1/models", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    yield "http://127.0.0.1:8012"
    server.should_exit = True


@pytest.fixture
def env(monkeypatch, tmp_path, fake_vllm_url):
    keys = tmp_path / "k.yaml"
    keys.write_text("[]")
    monkeypatch.setenv("API_KEYS_PATH", str(keys))
    monkeypatch.setenv("VLLM_URL", fake_vllm_url)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("RESULT_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")  # test DB
    return load_config()


def _make_tone(path: Path, duration: float = 1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"sine=frequency=440:duration={duration}", "-f", "wav", str(path)],
        capture_output=True, check=True,
    )


def test_transcribe_happy_path(env, tmp_path):
    conn = connect(env.db_path)
    run_migrations(conn)

    job_id = "test-job-1"
    audio = env.upload_dir / job_id
    audio.mkdir(parents=True)
    # Write the audio data to upload.bin (always the physical storage name)
    _make_tone(audio / "upload.bin", duration=1.5)

    # Use filename="upload.wav" so extension validation detects it as audio (.wav)
    # The worker reads the bytes from upload.bin on disk regardless of filename.
    create_job(conn, job_id=job_id, filename="upload.wav",
               hotwords_csv="", output_format="json")

    r = redis.from_url(env.redis_url)
    r.delete(f"job:{job_id}:events")  # clean

    transcribe_job(job_id=job_id, fake_scenario="happy")  # injectable for tests

    job = get_job(connect(env.db_path), job_id)
    assert job.status == "done"
    result_file = env.result_dir / job_id / "output.json"
    assert result_file.exists()
    data = json.loads(result_file.read_text())
    assert len(data["segments"]) >= 1
