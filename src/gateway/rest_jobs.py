"""GET /v1/jobs/{job_id}/result fallback endpoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from shared.repositories.job_repository import get_job

router = APIRouter()

_MEDIA_TYPES = {
    "json": "application/json",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
}


@router.get("/jobs/{job_id}/result")
async def get_result(
    job_id: str,
    request: Request,
    format: str = Query("json", pattern="^(json|srt|vtt)$"),
):
    conn = request.app.state.db
    job = get_job(conn, job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    if job.status != "done":
        raise HTTPException(404, f"job {job_id} not finished (status={job.status})")
    if not job.result_path:
        raise HTTPException(410, "result has been purged")

    json_path = Path(job.result_path)
    base_dir = json_path.parent

    if format == "json":
        target = json_path
    else:
        target = base_dir / f"output.{format}"
    media = _MEDIA_TYPES[format]

    if not target.exists():
        raise HTTPException(404, f"format {format} not available for job {job_id}")

    return FileResponse(target, media_type=media)
