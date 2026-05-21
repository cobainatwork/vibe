"""Input validation: extensions, sizes, durations.

Limits per spec §5.5.
"""
from __future__ import annotations

from pathlib import Path

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".webm", ".avi", ".mkv"}

MIN_DURATION_SEC = 0.5
MAX_DURATION_SEC = 3660.0  # 61 min, matches VIBEVOICE_MAX_AUDIO_DURATION


class ValidationError(Exception):
    """Validation failed; carries error_code + detail."""
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def check_filename_ext(filename: str) -> tuple[str, str]:
    """Return (kind, ext) where kind in {'audio','video'}; raise on bad ext."""
    from shared.error_codes import UNSUPPORTED_FORMAT

    ext = Path(filename).suffix.lower()
    if not ext:
        raise ValidationError(UNSUPPORTED_FORMAT, f"no extension in {filename!r}")
    if ext in AUDIO_EXTS:
        return ("audio", ext)
    if ext in VIDEO_EXTS:
        return ("video", ext)
    raise ValidationError(UNSUPPORTED_FORMAT, f"extension {ext} not allowed")


def check_file_size_mb(size_mb: float, *, max_mb: int) -> None:
    from shared.error_codes import FILE_TOO_LARGE
    if size_mb > max_mb:
        raise ValidationError(FILE_TOO_LARGE,
                              f"{size_mb:.1f}MB exceeds limit {max_mb}MB")


def check_audio_duration_sec(seconds: float) -> None:
    from shared.error_codes import AUDIO_DURATION_OUT_OF_RANGE
    if seconds < MIN_DURATION_SEC:
        raise ValidationError(AUDIO_DURATION_OUT_OF_RANGE,
                              f"{seconds:.2f}s shorter than {MIN_DURATION_SEC}s")
    if seconds > MAX_DURATION_SEC:
        raise ValidationError(AUDIO_DURATION_OUT_OF_RANGE,
                              f"{seconds:.2f}s exceeds {MAX_DURATION_SEC}s (61min)")
