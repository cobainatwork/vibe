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
    return TestClient(create_app())


HDR = {"X-API-Key": "t-key"}


def test_crud_full_cycle(client):
    # Create
    r = client.post(
        "/v1/hotword-groups",
        json={"name": "medical", "words": ["MRI", "CT"]},
        headers=HDR,
    )
    assert r.status_code == 201
    gid = r.json()["id"]

    # List
    r = client.get("/v1/hotword-groups", headers=HDR)
    assert r.status_code == 200
    assert any(g["name"] == "medical" for g in r.json())

    # Update
    r = client.put(f"/v1/hotword-groups/{gid}",
                   json={"words": ["MRI", "CT", "ECG"]}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["words"] == ["MRI", "CT", "ECG"]

    # Delete
    r = client.delete(f"/v1/hotword-groups/{gid}", headers=HDR)
    assert r.status_code == 204

    # Verify deleted
    r = client.get("/v1/hotword-groups", headers=HDR)
    assert not any(g["id"] == gid for g in r.json())


def test_create_duplicate_name_409(client):
    client.post("/v1/hotword-groups", json={"name": "dup", "words": ["a"]}, headers=HDR)
    r = client.post("/v1/hotword-groups", json={"name": "dup", "words": ["b"]}, headers=HDR)
    assert r.status_code == 409


def test_word_with_comma_rejected(client):
    r = client.post("/v1/hotword-groups",
                    json={"name": "bad", "words": ["has,comma"]}, headers=HDR)
    assert r.status_code == 400


def test_delete_unknown_404(client):
    r = client.delete("/v1/hotword-groups/9999", headers=HDR)
    assert r.status_code == 404
