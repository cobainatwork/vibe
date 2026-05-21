"""Shared utilities."""
from __future__ import annotations


def parse_csv(csv: str | None) -> list[str]:
    """Split CSV into stripped non-empty tokens."""
    if not csv:
        return []
    parts = (p.strip() for p in csv.split(","))
    return [p for p in parts if p]
