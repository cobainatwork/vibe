"""Transcribe job: full pipeline."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import redis

from shared import error_codes
from shared.config import load_config
from shared.db import connect
from shared.hotword_merger import merge_hotwords, parse_csv
from shared.repositories.hotword_repository import get_group_words
from shared.repositories.job_repository import (
    get_job, set_audio_duration, set_error, set_result_path, update_status,
)
from shared.result_writer import write_json, write_srt, write_vtt
from shared.validation import (
    ValidationError, check_audio_duration_sec, check_filename_ext,
)
from worker.audio_normalizer import (
    DecodingError, extract_audio_from_video, is_video_file, probe_duration_sec,
)
from worker.output_parser import parse_transcription
from worker.repetition_detector import RepetitionDetector
from worker.sse_parser import SSEEvent
from worker.vllm_client import VLLMClient

log = logging.getLogger(__name__)

MAX_HOTWORDS = 200
MAX_RETRIES = 3


def _publish(r: redis.Redis, channel: str, payload: dict) -> None:
    r.publish(channel, json.dumps(payload, ensure_ascii=False))


def _emit_error(r: redis.Redis, conn, job_id: str, code: str, detail: str) -> None:
    set_error(conn, job_id, code=code, detail=detail)
    _publish(r, f"job:{job_id}:events",
             {"type": "error", "code": code, "detail": detail, "job_id": job_id})


def transcribe_job(job_id: str, *, fake_scenario: str | None = None) -> None:
    """Entry point for an RQ-queued transcribe job."""
    cfg = load_config()
    conn = connect(cfg.db_path)
    r = redis.from_url(cfg.redis_url)
    channel = f"job:{job_id}:events"

    job = get_job(conn, job_id)
    if not job:
        log.warning("job %s not found", job_id)
        return

    update_status(conn, job_id, "running")

    job_upload_dir = cfg.upload_dir / job_id
    upload_bin = job_upload_dir / "upload.bin"
    if not upload_bin.exists():
        _emit_error(r, conn, job_id, error_codes.INTERNAL,
                    f"upload file missing for {job_id}")
        return

    # Step 1: validate filename + detect video
    try:
        kind, ext = check_filename_ext(job.filename or "upload.bin")
    except ValidationError as ve:
        _emit_error(r, conn, job_id, ve.code, ve.detail)
        return

    # Step 2: normalize → audio.mp3 if video
    if kind == "video":
        audio_path = job_upload_dir / "audio.mp3"
        try:
            extract_audio_from_video(upload_bin, audio_path)
        except DecodingError as e:
            _emit_error(r, conn, job_id, error_codes.DECODE_FAILED, str(e))
            return
    else:
        # Keep extension hint for ffmpeg in vllm side
        audio_path = job_upload_dir / f"audio{ext}"
        if not audio_path.exists():
            audio_path.symlink_to(upload_bin)

    # Step 3: probe duration
    try:
        duration_sec = probe_duration_sec(audio_path)
    except DecodingError as e:
        _emit_error(r, conn, job_id, error_codes.DECODE_FAILED, str(e))
        return

    try:
        check_audio_duration_sec(duration_sec)
    except ValidationError as ve:
        _emit_error(r, conn, job_id, ve.code, ve.detail)
        return

    set_audio_duration(conn, job_id, duration_sec)
    _publish(r, channel,
             {"type": "transcribing", "audio_duration": duration_sec})

    # Step 4: merge hotwords
    group_ids = [int(x) for x in parse_csv(job.hotword_group_ids_csv)]
    all_group_words = get_group_words(conn, group_ids)
    per_request = parse_csv(job.hotwords_csv)
    merged_words = merge_hotwords([all_group_words], per_request, max_words=MAX_HOTWORDS)
    hotwords_csv = ",".join(merged_words)

    # Step 5: call vLLM with retry-on-loop
    client = VLLMClient(base_url=cfg.vllm_url)
    detector = RepetitionDetector(min_pattern_len=10, min_repeats=10, window_size=400)
    accumulated = ""
    retry = 0
    final_text: str | None = None
    extra_query = {"scenario": fake_scenario} if fake_scenario else None

    while retry <= MAX_RETRIES:
        temperature = 0.0 if retry == 0 else 0.1 + 0.1 * retry  # 0.2/0.3/0.4
        try:
            iterator = client.stream_transcribe(
                audio_path=str(audio_path),
                duration_sec=duration_sec,
                hotwords_csv=hotwords_csv,
                extra_query=extra_query,
                temperature=temperature,
                assistant_prefix=accumulated if accumulated else None,
            )
        except RuntimeError as e:
            _emit_error(r, conn, job_id, error_codes.INFERENCE_ERROR, str(e))
            return

        new_text = ""
        loop_detected = False
        try:
            for ev in iterator:
                if ev.done:
                    final_text = accumulated + new_text
                    break
                if not ev.content:
                    continue
                new_text += ev.content
                is_loop, good_end = detector.add_text(ev.content)
                if is_loop:
                    accumulated = (accumulated + new_text)[:good_end]
                    detector.reset(accumulated)
                    loop_detected = True
                    break
        except RuntimeError as e:
            _emit_error(r, conn, job_id, error_codes.INFERENCE_ERROR, str(e))
            return

        if not loop_detected:
            break
        retry += 1

    if final_text is None:
        _emit_error(r, conn, job_id, error_codes.INFERENCE_ERROR,
                    "exceeded retries without completion")
        return

    # Step 6: parse + write results
    segments = parse_transcription(final_text)
    if not segments:
        _publish(r, channel,
                 {"type": "warning", "code": error_codes.PARTIAL_PARSE,
                  "detail": "could not parse JSON; raw text saved"})

    out_dir = cfg.result_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_text_path = out_dir / "raw_text.txt"
    raw_text_path.write_text(final_text, encoding="utf-8")

    result_path = out_dir / "output.json"
    write_json(segments, result_path)
    if job.output_format == "srt":
        write_srt(segments, out_dir / "output.srt")
    elif job.output_format == "vtt":
        write_vtt(segments, out_dir / "output.vtt")

    set_result_path(conn, job_id, str(result_path), str(raw_text_path))

    # Stream segments to clients via pubsub
    for seg in segments:
        _publish(r, channel, {"type": "segment", "data": seg})

    update_status(conn, job_id, "done")
    _publish(r, channel,
             {"type": "done",
              "summary": {"segments": len(segments)}})

    # Cleanup uploads (privacy)
    if cfg.retain_upload_days == 0:
        shutil.rmtree(job_upload_dir, ignore_errors=True)
