import pytest
import uvicorn
import threading
import time

from worker.vllm_client import VLLMClient


@pytest.fixture(scope="module")
def fake_vllm_url():
    from tests.fixtures.fake_vllm import app
    config = uvicorn.Config(app, host="127.0.0.1", port=8011, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # wait for ready
    for _ in range(50):
        try:
            import httpx
            httpx.get("http://127.0.0.1:8011/v1/models", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    yield "http://127.0.0.1:8011"
    server.should_exit = True


def test_stream_returns_content_chunks(fake_vllm_url):
    client = VLLMClient(base_url=fake_vllm_url)
    chunks = list(
        client.stream_transcribe(
            audio_path="/app/uploads/x.mp3",
            duration_sec=5.2,
            hotwords_csv="",
            extra_query={"scenario": "happy"},
        )
    )
    text = "".join(c.content for c in chunks if not c.done)
    assert "你好" in text
    assert "嗨" in text
    assert chunks[-1].done is True


def test_stream_handles_5xx(fake_vllm_url):
    client = VLLMClient(base_url=fake_vllm_url)
    with pytest.raises(RuntimeError):
        list(client.stream_transcribe(
            audio_path="/app/uploads/x.mp3",
            duration_sec=5.0,
            hotwords_csv="",
            extra_query={"scenario": "error_5xx"},
        ))
