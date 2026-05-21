"""GET /v1/models/current."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()

VERSION_FILE = Path("/opt/vibevoice/current_model/version.json")


@router.get("/models/current")
async def current_model(request: Request):
    if VERSION_FILE.exists():
        data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
        return data
    # Fallback: derive from symlink target
    p = Path("/opt/vibevoice/current_model")
    if p.is_symlink():
        target = p.readlink().name
        return {"name": "vibevoice", "version": target, "loaded_at": None}
    return {"name": "vibevoice", "version": "unknown", "loaded_at": None}
