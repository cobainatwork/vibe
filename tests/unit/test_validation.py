import pytest

from shared.validation import (
    ValidationError, check_filename_ext, check_file_size_mb,
    check_audio_duration_sec, AUDIO_EXTS, VIDEO_EXTS,
)


def test_audio_ext_allowed():
    assert check_filename_ext("a.mp3") == ("audio", ".mp3")
    assert check_filename_ext("b.WAV") == ("audio", ".wav")
    assert check_filename_ext("c.flac") == ("audio", ".flac")


def test_video_ext_allowed():
    assert check_filename_ext("a.mp4") == ("video", ".mp4")
    assert check_filename_ext("b.MOV") == ("video", ".mov")


def test_unsupported_ext_raises():
    with pytest.raises(ValidationError):
        check_filename_ext("a.txt")


def test_missing_ext_raises():
    with pytest.raises(ValidationError):
        check_filename_ext("noext")


def test_file_size_within_limit():
    check_file_size_mb(500, max_mb=1024)  # no raise


def test_file_size_over_limit_raises():
    with pytest.raises(ValidationError):
        check_file_size_mb(2000, max_mb=1024)


def test_audio_duration_in_range():
    check_audio_duration_sec(60.0)  # no raise


def test_audio_duration_too_short_raises():
    with pytest.raises(ValidationError):
        check_audio_duration_sec(0.3)


def test_audio_duration_too_long_raises():
    with pytest.raises(ValidationError):
        check_audio_duration_sec(3700.0)


def test_audio_video_ext_sets_known():
    assert ".mp3" in AUDIO_EXTS
    assert ".mp4" in VIDEO_EXTS
