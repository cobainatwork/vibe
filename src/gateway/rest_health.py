"""GET /v1/health."""
from __future__ import annotations

import shutil

import httpx
import redis
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    cfg = request.app.state.config
    # vLLM check
    vllm_ready = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{cfg.vllm_url}/v1/models")
            vllm_ready = r.status_code == 200
    except Exception:
        pass

    # Queue depth
    queue_depth = 0
    try:
        r = redis.from_url(cfg.redis_url)
        queue_depth = r.llen("rq:queue:transcribe")
    except Exception:
        pass

    # Disk usage
    upload_parent = cfg.upload_dir.parent if cfg.upload_dir.exists() else cfg.upload_dir
    try:
        usage = shutil.disk_usage(str(upload_parent))
    except Exception:
        usage = shutil.disk_usage("/")
    disk_pct = 100.0 - (usage.free / usage.total * 100.0)

    status = "ok" if vllm_ready else "degraded"
    return {
        "status": status,
        "vllm_ready": vllm_ready,
        "queue_depth": queue_depth,
        "disk_usage_pct": round(disk_pct, 1),
    }
