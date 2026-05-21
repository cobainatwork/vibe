import subprocess
from pathlib import Path

import pytest

from worker.audio_normalizer import (
    DecodingError,
    extract_audio_from_video,
    is_video_file,
    probe_duration_sec,
)


def _make_tone_wav(path: Path, duration_sec: float = 1.0):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"sine=frequency=440:duration={duration_sec}", str(path)]
    subprocess.run(cmd, capture_output=True, check=True)


def test_probe_duration_real_file(tmp_path):
    wav = tmp_path / "tone.wav"
    _make_tone_wav(wav, 2.0)
    dur = probe_duration_sec(wav)
    assert 1.9 < dur < 2.1


def test_probe_duration_corrupt_file_raises(tmp_path):
    bad = tmp_path / "corrupt.mp3"
    bad.write_bytes(b"\x00\x00not_audio\x00")
    with pytest.raises(DecodingError):
        probe_duration_sec(bad)


def test_is_video_file_by_extension():
    assert is_video_file("a.mp4") is True
    assert is_video_file("a.MOV") is True
    assert is_video_file("a.mp3") is False


def test_extract_audio_from_video(tmp_path):
    # Build a tiny mp4 by combining tone + black video
    mp4 = tmp_path / "in.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "color=black:size=64x64:duration=1",
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
        str(mp4),
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    out = tmp_path / "out.mp3"
    extract_audio_from_video(mp4, out)
    assert out.exists()
    dur = probe_duration_sec(out)
    assert 0.8 < dur < 1.2
