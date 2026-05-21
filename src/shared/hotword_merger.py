"""Hotword merging: groups + per-request → dedup → cap.

Order preserved: first groups (in id order), then per-request additions.
"""
from __future__ import annotations


def parse_csv(csv: str | None) -> list[str]:
    if not csv:
        return []
    parts = (p.strip() for p in csv.split(","))
    return [p for p in parts if p]


def merge_hotwords(
    group_words_lists: list[list[str]],
    per_request_words: list[str],
    *,
    max_words: int,
) -> list[str]:
    """Merge multiple hotword sources, dedupe (preserving first occurrence order), cap."""
    seen: set[str] = set()
    out: list[str] = []
    for group_words in group_words_lists:
        for w in group_words:
            if w not in seen:
                seen.add(w)
                out.append(w)
                if len(out) >= max_words:
                    return out
    for w in per_request_words:
        if w not in seen:
            seen.add(w)
            out.append(w)
            if len(out) >= max_words:
                return out
    return out
