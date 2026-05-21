"""Write transcription results in json/srt/vtt formats."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def format_timestamp_srt(seconds: float) -> str:
    """HH:MM:SS,mmm"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = round((seconds - int(seconds)) * 1000)
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """HH:MM:SS.mmm (period instead of comma)"""
    return format_timestamp_srt(seconds).replace(",", ".")


def write_json(segments: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"segments": segments, "total_segments": len(segments)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def write_srt(segments: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = format_timestamp_srt(seg["start_time"])
        end = format_timestamp_srt(seg["end_time"])
        speaker = seg.get("speaker_id", 0)
        text = seg.get("text", "")
        lines.append(f"{i}\n{start} --> {end}\n[Speaker {speaker}] {text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_vtt(segments: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["WEBVTT\n"]
    for seg in segments:
        start = format_timestamp_vtt(seg["start_time"])
        end = format_timestamp_vtt(seg["end_time"])
        speaker = seg.get("speaker_id", 0)
        text = seg.get("text", "")
        lines.append(f"{start} --> {end}\n[Speaker {speaker}] {text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
