"""Config loader: reads env vars + api_keys.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    gateway_port: int
    max_file_size_mb: int
    queue_max_depth: int
    ws_idle_timeout_sec: int
    retain_upload_days: int
    retain_result_days: int
    retain_job_record_days: int
    upload_dir: Path
    result_dir: Path
    db_path: Path
    redis_url: str
    vllm_url: str
    api_keys: dict[str, str]  # key → name


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


def _path_env(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def _load_api_keys(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"API keys file not found: {path}")
    with path.open(encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []
    return {entry["key"]: entry["name"] for entry in entries}


def load_config() -> Config:
    api_keys_path = _path_env("API_KEYS_PATH", "/app/config/api_keys.yaml")
    return Config(
        gateway_port=_int_env("GATEWAY_PORT", 8000),
        max_file_size_mb=_int_env("MAX_FILE_SIZE_MB", 1024),
        queue_max_depth=_int_env("QUEUE_MAX_DEPTH", 100),
        ws_idle_timeout_sec=_int_env("WS_IDLE_TIMEOUT_SEC", 60),
        retain_upload_days=_int_env("RETAIN_UPLOAD_DAYS", 0),
        retain_result_days=_int_env("RETAIN_RESULT_DAYS", 30),
        retain_job_record_days=_int_env("RETAIN_JOB_RECORD_DAYS", 90),
        upload_dir=_path_env("UPLOAD_DIR", "/app/data/uploads"),
        result_dir=_path_env("RESULT_DIR", "/app/data/results"),
        db_path=_path_env("DB_PATH", "/app/data/db/vibevoice.db"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        vllm_url=os.environ.get("VLLM_URL", "http://vllm:8001"),
        api_keys=_load_api_keys(api_keys_path),
    )
