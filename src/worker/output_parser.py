"""Parse model's raw text output into structured segments.

We delegate to upstream `vibevoice.processor.vibevoice_asr_processor`
`post_process_transcription` (vibevoice_src/.../vibevoice_asr_processor.py:490-565)
which already handles markdown wrapping, key normalization
(Start time/Start → start_time, etc.), and malformed JSON gracefully.

Since the upstream module requires a tokenizer to instantiate, we just
import the standalone function logic and re-implement it as a free function
here to avoid the heavy dependency.
"""
from __future__ import annotations

import json
from typing import Any

_KEY_MAPPING = {
    "Start time": "start_time",
    "Start": "start_time",
    "End time": "end_time",
    "End": "end_time",
    "Speaker ID": "speaker_id",
    "Speaker": "speaker_id",
    "Content": "text",
}


def _extract_json_str(text: str) -> str:
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        return text[start:end].strip() if end != -1 else ""
    start = text.find("[")
    if start == -1:
        start = text.find("{")
    if start == -1:
        return text
    bracket_count = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch in "[{":
            bracket_count += 1
        elif ch in "]}":
            bracket_count -= 1
            if bracket_count == 0:
                return text[start:i + 1]
    return text[start:]


def parse_transcription(text: str) -> list[dict[str, Any]]:
    """Parse model output text → list of segments with normalized keys."""
    if not text:
        return []
    json_str = _extract_json_str(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]

    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized = {}
        for src, dst in _KEY_MAPPING.items():
            if src in item:
                normalized[dst] = item[src]
        if normalized:
            out.append(normalized)
    return out
