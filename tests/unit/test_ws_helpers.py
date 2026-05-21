"""Unit tests for ws_transcribe helper functions."""
from __future__ import annotations

import asyncio

import pytest
import redis

from gateway.ws_transcribe import _enqueue_job, _receive_start_frame

# ---------------------------------------------------------------------------
# _receive_start_frame tests
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Minimal fake websocket for _receive_start_frame testing."""

    def __init__(self, receive_json_value=None, raise_exc=None):
        self._value = receive_json_value
        self._raise_exc = raise_exc
        self.closed_code: int | None = None
        self.closed = False
        self.sent: list = []
        self.scope: dict = {"_job_id": "testjob"}

    async def receive_json(self):
        if self._raise_exc:
            raise self._raise_exc
        return self._value

    async def close(self, code=None):
        self.closed = True
        self.closed_code = code

    async def send_json(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_receive_start_frame_happy_path():
    """Returns the start dict when a valid start frame is received."""
    ws = _FakeWebSocket(receive_json_value={"type": "start", "filename": "audio.mp3"})
    result = await _receive_start_frame(ws, idle_timeout_sec=5.0)
    assert result is not None
    assert result["type"] == "start"
    assert result["filename"] == "audio.mp3"
    assert not ws.closed


@pytest.mark.asyncio
async def test_receive_start_frame_non_start_returns_none():
    """Returns None and closes websocket when frame type is not 'start'."""
    ws = _FakeWebSocket(receive_json_value={"type": "unexpected", "filename": "x.mp3"})
    result = await _receive_start_frame(ws, idle_timeout_sec=5.0)
    assert result is None
    assert ws.closed
    assert len(ws.sent) == 1
    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["detail"] == "expected start frame"


@pytest.mark.asyncio
async def test_receive_start_frame_timeout_returns_none():
    """Returns None and closes with 1001 on TimeoutError."""
    ws = _FakeWebSocket(raise_exc=asyncio.TimeoutError())
    result = await _receive_start_frame(ws, idle_timeout_sec=0.001)
    assert result is None
    assert ws.closed
    assert ws.closed_code == 1001


# ---------------------------------------------------------------------------
# _enqueue_job tests (against real Redis at localhost:6379/15)
# ---------------------------------------------------------------------------

REDIS_TEST_URL = "redis://localhost:6379/15"
TEST_JOB_ID = "unittest_enqueue_001"


@pytest.fixture(autouse=False)
def cleanup_redis_queue():
    """Remove test job from Redis before and after the test."""
    r = redis.Redis.from_url(REDIS_TEST_URL)
    r.delete("rq:queue:transcribe")
    yield
    r.delete("rq:queue:transcribe")
    r.close()


@pytest.mark.asyncio
async def test_enqueue_job_adds_item_to_queue(cleanup_redis_queue):
    """_enqueue_job enqueues a job; LLEN of rq:queue:transcribe increases by 1."""
    r = redis.Redis.from_url(REDIS_TEST_URL)
    try:
        before = r.llen("rq:queue:transcribe")
        await _enqueue_job(REDIS_TEST_URL, TEST_JOB_ID)
        after = r.llen("rq:queue:transcribe")
        assert after == before + 1
    finally:
        r.close()
