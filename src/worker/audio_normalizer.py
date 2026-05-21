"""Audio probing and video → audio extraction via ffmpeg/ffprobe."""
from __future__ import annotations

import subprocess
from pathlib import Path

from shared.validation import VIDEO_EXTS


class DecodingError(Exception):
    pass


def is_video_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTS


def probe_duration_sec(path: Path) -> float:
    """Return duration via ffprobe; raise DecodingError on failure."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise DecodingError(f"ffprobe failed: {e}") from e
    text = out.decode("utf-8", errors="replace").strip()
    if not text or text == "N/A":
        raise DecodingError(f"ffprobe could not determine duration of {path}")
    try:
        return float(text)
    except ValueError as e:
        raise DecodingError(f"ffprobe returned non-numeric: {text!r}") from e


def extract_audio_from_video(src: Path, dst: Path) -> None:
    """Extract audio track to mp3."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-vn",                   # no video
                "-acodec", "libmp3lame",
                "-q:a", "2",
                str(dst),
            ],
            capture_output=True,
            check=True,
            timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise DecodingError(f"ffmpeg extract failed: {e}") from e
