import json

import pytest

from shared.result_writer import (
    write_json, write_srt, write_vtt, format_timestamp_srt, format_timestamp_vtt,
)


SEGMENTS = [
    {"start_time": 0.0, "end_time": 2.5, "speaker_id": 0, "text": "你好"},
    {"start_time": 2.5, "end_time": 5.2, "speaker_id": 1, "text": "嗨"},
]


def test_format_timestamp_srt():
    assert format_timestamp_srt(0.0) == "00:00:00,000"
    assert format_timestamp_srt(65.5) == "00:01:05,500"
    assert format_timestamp_srt(3661.123) == "01:01:01,123"


def test_format_timestamp_vtt():
    assert format_timestamp_vtt(0.0) == "00:00:00.000"
    assert format_timestamp_vtt(65.5) == "00:01:05.500"


def test_write_json(tmp_path):
    path = tmp_path / "out.json"
    write_json(SEGMENTS, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["segments"] == SEGMENTS
    assert data["total_segments"] == 2


def test_write_srt(tmp_path):
    path = tmp_path / "out.srt"
    write_srt(SEGMENTS, path)
    content = path.read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:02,500\n[Speaker 0] 你好" in content
    assert "2\n00:00:02,500 --> 00:00:05,200\n[Speaker 1] 嗨" in content


def test_write_vtt(tmp_path):
    path = tmp_path / "out.vtt"
    write_vtt(SEGMENTS, path)
    content = path.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in content
    assert "[Speaker 0] 你好" in content


def test_write_empty_segments(tmp_path):
    write_json([], tmp_path / "e.json")
    write_srt([], tmp_path / "e.srt")
    write_vtt([], tmp_path / "e.vtt")
    # all should succeed without raising
