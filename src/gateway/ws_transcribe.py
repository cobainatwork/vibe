"""WS /v1/transcribe handler.

Spec §5.2 state machine.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid

import redis.asyncio as aioredis
import rq
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis import Redis as SyncRedis

from gateway.upload_writer import MaxSizeExceeded, UploadWriter
from shared import error_codes
from shared.auth import AuthError, verify_api_key
from shared.db import TRANSCRIBE_QUEUE_NAME, TRANSCRIBE_QUEUE_REDIS_KEY
from shared.repositories.job_repository import create_job, update_status
from shared.validation import ValidationError, check_filename_ext

log = logging.getLogger(__name__)

_ACK_THRESHOLD_BYTES = 1024 * 1024  # 1 MB: send ack every time this much received

router = APIRouter()


def _enqueue_sync(redis_url: str, job_id: str) -> None:
    conn = SyncRedis.from_url(redis_url, socket_connect_timeout=2)
    try:
        rq.Queue(TRANSCRIBE_QUEUE_NAME, connection=conn).enqueue(
            "worker.tasks.transcribe.transcribe_job",
            job_id=job_id,
            job_timeout=3600 * 2,
        )
    finally:
        conn.close()


async def _receive_start_frame(websocket: WebSocket, idle_timeout_sec: float) -> dict | None:
    """Wait for the 'start' frame after handshake.

    Returns parsed dict or None on error (caller closes).
    """
    job_id = websocket.scope.get("_job_id", "")
    try:
        start_msg = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=idle_timeout_sec,
        )
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close(code=1001)
        return None

    if start_msg.get("type") != "start":
        await websocket.send_json({
            "type": "error", "code": error_codes.INTERNAL,
            "detail": "expected start frame", "job_id": job_id,
        })
        await websocket.close()
        return None

    return start_msg


async def _receive_upload(
    websocket: WebSocket,
    writer: UploadWriter,
    idle_timeout_sec: float,
    max_file_size_mb: int,
    job_id: str,
    # DB params needed only on disconnect to mark aborted
    db,
    filename: str,
    hotwords_csv: str,
    hotword_group_ids_csv: str,
    output_format: str,
    upload_target,
) -> bool:
    """Receive binary chunks + emit ACK every 1MB.

    Returns True on 'eof', False on disconnect/timeout/size-exceeded.
    Caller handles cleanup of writer + sending error frames.
    """
    last_ack_bytes = 0
    try:
        while True:
            msg = await asyncio.wait_for(
                websocket.receive(),
                timeout=idle_timeout_sec,
            )
            if msg.get("type") == "websocket.disconnect":
                writer.close()
                create_job(db, job_id=job_id, filename=filename,
                           hotwords_csv=hotwords_csv,
                           hotword_group_ids_csv=hotword_group_ids_csv,
                           output_format=output_format)
                update_status(db, job_id, "aborted")
                shutil.rmtree(upload_target.parent, ignore_errors=True)
                return False

            if "bytes" in msg and msg["bytes"]:
                try:
                    writer.write(msg["bytes"])
                except MaxSizeExceeded:
                    await websocket.send_json({
                        "type": "error", "code": error_codes.FILE_TOO_LARGE,
                        "detail": f"max {max_file_size_mb}MB",
                        "job_id": job_id,
                    })
                    writer.close()
                    await websocket.close()
                    return False
                if writer.total_bytes - last_ack_bytes >= _ACK_THRESHOLD_BYTES:
                    last_ack_bytes = writer.total_bytes
                    await websocket.send_json({
                        "type": "ack", "bytes_received": writer.total_bytes,
                    })
                continue

            if "text" in msg:
                try:
                    obj = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "eof":
                    return True
    except asyncio.TimeoutError:
        await websocket.send_json({
            "type": "error", "code": error_codes.INTERNAL,
            "detail": "idle timeout", "job_id": job_id,
        })
        writer.close()
        await websocket.close()
        return False
    except WebSocketDisconnect:
        writer.close()
        return False


async def _enqueue_job(redis_url: str, job_id: str) -> None:
    """Enqueue the transcribe job via run_in_executor. Wraps _enqueue_sync. Raises on failure."""
    await asyncio.get_event_loop().run_in_executor(None, _enqueue_sync, redis_url, job_id)


async def _forward_events(websocket: WebSocket, redis_url: str, job_id: str) -> None:
    """Subscribe to job:{job_id}:events pubsub channel.

    Forward messages to WS until done/error/disconnect.
    """
    try:
        pubsub_r = aioredis.from_url(redis_url)
        pubsub = pubsub_r.pubsub()
        channel = f"job:{job_id}:events"
        await pubsub.subscribe(channel)
        try:
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                payload = raw["data"]
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                await websocket.send_json(event)
                if event.get("type") in ("done", "error"):
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
    except Exception as exc:
        log.warning("Pubsub setup failed for job %s: %s", job_id, exc)


@router.websocket("/transcribe")
async def ws_transcribe(websocket: WebSocket):
    cfg = websocket.app.state.config
    db = websocket.app.state.db

    # Auth: X-API-Key header — HTTP middleware does NOT cover WS
    try:
        verify_api_key(websocket.headers.get("x-api-key"), cfg.api_keys)
    except AuthError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    job_id = uuid.uuid4().hex[:12]
    websocket.scope["_job_id"] = job_id

    start = await _receive_start_frame(websocket, cfg.ws_idle_timeout_sec)
    if start is None:
        return

    filename = start.get("filename", "upload.bin")
    hotwords_csv = start.get("hotwords") or ""
    hotword_group_ids = start.get("hotword_group_ids") or []
    output_format = start.get("output_format", "json")
    if output_format not in {"json", "srt", "vtt"}:
        output_format = "json"

    # Check queue depth before going further (best-effort; failure is non-fatal)
    depth_r = None
    try:
        depth_r = aioredis.from_url(cfg.redis_url, socket_connect_timeout=2)
        queue_depth = await depth_r.llen(TRANSCRIBE_QUEUE_REDIS_KEY)  # type: ignore[misc]
        if queue_depth >= cfg.queue_max_depth:
            await websocket.send_json({
                "type": "error", "code": error_codes.QUEUE_FULL,
                "detail": "queue depth exceeded", "retry_after_sec": 60,
                "job_id": job_id,
            })
            await websocket.close()
            return
    except Exception as exc:
        log.debug("Redis queue-depth check failed (best-effort): %s", exc)
    finally:
        if depth_r is not None:
            await depth_r.aclose()

    await websocket.send_json({"type": "ready", "job_id": job_id})

    upload_target = cfg.upload_dir / job_id / "upload.bin"
    writer = UploadWriter(upload_target, max_bytes=cfg.max_file_size_mb * 1024 * 1024)
    hotword_group_ids_csv = ",".join(map(str, hotword_group_ids))

    eof_ok = await _receive_upload(
        websocket, writer, cfg.ws_idle_timeout_sec,
        cfg.max_file_size_mb, job_id,
        db, filename, hotwords_csv, hotword_group_ids_csv, output_format,
        upload_target,
    )
    if not eof_ok:
        return

    writer.close()

    try:
        check_filename_ext(filename)
    except ValidationError as ve:
        await websocket.send_json({
            "type": "error", "code": ve.code, "detail": ve.detail,
            "job_id": job_id,
        })
        await websocket.close()
        return

    try:
        await _enqueue_job(cfg.redis_url, job_id)
    except Exception as exc:
        log.warning("Failed to enqueue job %s: %s", job_id, exc)
        await websocket.send_json({
            "type": "error", "code": error_codes.SERVICE_UNAVAILABLE,
            "detail": "queue unavailable", "job_id": job_id,
        })
        await websocket.close()
        return

    create_job(
        db, job_id=job_id, filename=filename,
        hotwords_csv=hotwords_csv,
        hotword_group_ids_csv=hotword_group_ids_csv,
        output_format=output_format,
    )

    await _forward_events(websocket, cfg.redis_url, job_id)

    try:
        await websocket.close()
    except Exception as exc:
        log.debug("close error (job %s): %s", job_id, exc)
