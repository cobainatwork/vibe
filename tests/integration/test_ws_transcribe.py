import asyncio
import json
import os
import subprocess
from pathlib import Path

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
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "10")
    from gateway.main import create_app
    return TestClient(create_app())


def test_ws_handshake_then_ready(client):
    with client.websocket_connect(
        "/v1/transcribe", headers={"X-API-Key": "t-key"}
    ) as ws:
        ws.send_json({"type": "start", "filename": "test.mp3"})
        msg = ws.receive_json()
        assert msg["type"] == "ready"
        assert "job_id" in msg
        ws.close()


def test_ws_invalid_auth_rejected(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/transcribe") as ws:
            ws.send_json({"type": "start"})
            ws.receive_json()


def test_ws_unsupported_format_error(client):
    with client.websocket_connect(
        "/v1/transcribe", headers={"X-API-Key": "t-key"}
    ) as ws:
        ws.send_json({"type": "start", "filename": "doc.txt"})
        msg = ws.receive_json()
        assert msg["type"] == "ready"  # ready issued before validation
        ws.send_bytes(b"some bytes")
        ws.send_json({"type": "eof"})
        msg = ws.receive_json()
        # may be transcribing first or error; loop
        while msg.get("type") not in {"error", "done"}:
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "UNSUPPORTED_FORMAT"
