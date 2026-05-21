"""Parse vLLM SSE stream into events.

vLLM's OpenAI-compatible /v1/chat/completions returns:
    data: {json}\n
    data: {json}\n
    data: [DONE]\n
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass
class SSEEvent:
    content: str = ""
    done: bool = False


def parse_sse_lines(lines: Iterable[str]) -> Iterator[SSEEvent]:
    """Yield SSEEvent per data line.

    Tolerant: skips non-data lines, malformed JSON, and missing fields.
    """
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):].strip()
        if payload == "[DONE]":
            yield SSEEvent(done=True)
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        try:
            content = obj["choices"][0].get("delta", {}).get("content", "")
        except (KeyError, IndexError, TypeError):
            content = ""
        yield SSEEvent(content=content, done=False)
