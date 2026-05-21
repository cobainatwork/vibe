"""End-to-end tests against a real running V-Client deployment.

Trigger: pytest -m e2e
Requires: docker compose up -d with everything healthy.
"""
import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
import websockets

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")
API_KEY = os.environ.get("E2E_API_KEY", "change-me-to-a-long-random-string")
FIXTURE = Path(__file__).parent.parent / "fixtures" / "audio" / "zh_tw_short.wav"


pytestmark = pytest.mark.e2e


def test_health_ready():
    r = httpx.get(f"{BASE}/v1/health", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["vllm_ready"] is True, f"vllm not ready: {body}"


@pytest.mark.asyncio
async def test_ws_transcribe_zh_tw():
    if not FIXTURE.exists():
        pytest.skip(f"fixture {FIXTURE} not present")
    audio = FIXTURE.read_bytes()

    async with websockets.connect(
        f"{WS_BASE}/v1/transcribe",
        additional_headers={"X-API-Key": API_KEY},
    ) as ws:
        await ws.send(json.dumps({"type": "start", "filename": FIXTURE.name}))
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"
        job_id = ready["job_id"]

        await ws.send(audio)
        await ws.send(json.dumps({"type": "eof"}))

        segments = []
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "segment":
                segments.append(msg["data"])
            elif msg.get("type") == "done":
                break
            elif msg.get("type") == "error":
                pytest.fail(f"error: {msg}")

        assert len(segments) > 0


@pytest.mark.asyncio
async def test_ws_with_hotwords():
    if not FIXTURE.exists():
        pytest.skip()
    audio = FIXTURE.read_bytes()
    async with websockets.connect(
        f"{WS_BASE}/v1/transcribe",
        additional_headers={"X-API-Key": API_KEY},
    ) as ws:
        await ws.send(json.dumps({
            "type": "start", "filename": FIXTURE.name,
            "hotwords": "微軟,VibeVoice",
        }))
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"
        await ws.send(audio)
        await ws.send(json.dumps({"type": "eof"}))
        # consume until done
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") in ("done", "error"):
                if msg["type"] == "error":
                    pytest.fail(f"error: {msg}")
                break


def test_rest_fallback_after_disconnect():
    # Hard to simulate without a real run; placeholder for manual verification
    pass
