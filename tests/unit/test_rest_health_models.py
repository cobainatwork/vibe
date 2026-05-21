import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    keys = tmp_path / "k.yaml"
    keys.write_text(
        "- {name: tester, key: t-key}\n"
    )
    monkeypatch.setenv("API_KEYS_PATH", str(keys))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "u"))
    monkeypatch.setenv("RESULT_DIR", str(tmp_path / "r"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    from gateway.main import create_app
    return create_app()


def test_health_returns_status(app):
    c = TestClient(app)
    resp = c.get("/v1/health", headers={"X-API-Key": "t-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "vllm_ready" in body
    assert "queue_depth" in body


def test_models_current_requires_auth(app):
    c = TestClient(app)
    resp = c.get("/v1/models/current")
    assert resp.status_code == 401


def test_models_current_with_auth(app):
    c = TestClient(app)
    resp = c.get("/v1/models/current", headers={"X-API-Key": "t-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body
    assert "loaded_at" in body
