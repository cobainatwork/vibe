import pytest
import yaml

from shared.config import load_config


def test_load_config_from_env(monkeypatch, tmp_path):
    api_keys_file = tmp_path / "keys.yaml"
    api_keys_file.write_text(yaml.safe_dump([
        {"name": "ops", "key": "secret-1"},
        {"name": "cron", "key": "secret-2"},
    ]))

    monkeypatch.setenv("GATEWAY_PORT", "8080")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "500")
    monkeypatch.setenv("API_KEYS_PATH", str(api_keys_file))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("VLLM_URL", "http://localhost:8001")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("RESULT_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    cfg = load_config()

    assert cfg.gateway_port == 8080
    assert cfg.max_file_size_mb == 500
    assert cfg.api_keys == {"secret-1": "ops", "secret-2": "cron"}
    assert cfg.redis_url == "redis://localhost:6379/0"


def test_default_values(monkeypatch, tmp_path):
    keys = tmp_path / "k.yaml"
    keys.write_text("[]")
    monkeypatch.setenv("API_KEYS_PATH", str(keys))
    monkeypatch.delenv("GATEWAY_PORT", raising=False)
    monkeypatch.delenv("MAX_FILE_SIZE_MB", raising=False)

    cfg = load_config()
    assert cfg.gateway_port == 8000
    assert cfg.max_file_size_mb == 1024
    assert cfg.queue_max_depth == 100
    assert cfg.ws_idle_timeout_sec == 60


def test_missing_api_keys_file_raises(monkeypatch):
    monkeypatch.setenv("API_KEYS_PATH", "/nonexistent/file.yaml")
    with pytest.raises(FileNotFoundError):
        load_config()
