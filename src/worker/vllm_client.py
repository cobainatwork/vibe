"""HTTP+SSE client for vLLM /v1/chat/completions.

Uses file:// audio URL (avoids base64 / 200MB nginx limit).
"""
from __future__ import annotations

from typing import Iterator

import httpx

from shared.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from worker.sse_parser import SSEEvent, parse_sse_lines


class VLLMClient:
    def __init__(self, *, base_url: str, request_timeout_sec: float = 1800.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = request_timeout_sec

    def stream_transcribe(
        self,
        *,
        audio_path: str,                    # path INSIDE vllm container, e.g. /app/uploads/{id}/audio.mp3
        duration_sec: float,
        hotwords_csv: str,
        extra_query: dict[str, str] | None = None,
        max_tokens: int = 32768,
        temperature: float = 0.0,
        assistant_prefix: str | None = None,
    ) -> Iterator[SSEEvent]:
        """Stream SSE events from vLLM."""
        url = f"{self.base_url}/v1/chat/completions"
        prompt_text = build_user_prompt(
            duration_sec=duration_sec, hotwords_csv=hotwords_csv
        )
        audio_url = f"file://{audio_path}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "audio_url", "audio_url": {"url": audio_url}},
                    {"type": "text", "text": prompt_text},
                ],
            },
        ]
        if assistant_prefix:
            messages.append({"role": "assistant", "content": assistant_prefix})

        payload = {
            "model": "vibevoice",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 1.0 if temperature == 0.0 else 0.95,
            "stream": True,
        }
        params = extra_query or {}

        with httpx.stream(
            "POST", url, json=payload, params=params, timeout=self.timeout
        ) as resp:
            if resp.status_code >= 400:
                raise RuntimeError(f"vLLM {resp.status_code}: {resp.read()[:500]}")
            yield from parse_sse_lines(resp.iter_lines())
