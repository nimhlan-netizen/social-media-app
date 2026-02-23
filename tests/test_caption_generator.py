"""
Tests for caption_generator.py — no API calls, pure Python logic.
"""
from app.services.caption_generator import (
    seconds_to_srt_time,
    transcript_to_srt,
    _srt_to_seconds,
    adjust_srt_timing,
)
import os
import tempfile


def test_seconds_to_srt_time_basic():
    assert seconds_to_srt_time(0) == "00:00:00,000"
    assert seconds_to_srt_time(1.5) == "00:00:01,500"
    assert seconds_to_srt_time(61.25) == "00:01:01,250"
    assert seconds_to_srt_time(3661.1) == "01:01:01,100"


def test_srt_to_seconds():
    assert _srt_to_seconds("00:00:01,500") == 1.5
    assert _srt_to_seconds("00:01:01,250") == 61.25


def test_transcript_to_srt_creates_file():
    transcript = [
        {"start": 0.0, "end": 2.5, "text": "Hello world"},
        {"start": 2.5, "end": 5.0, "text": "This is a test"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
        path = f.name

    try:
        result = transcript_to_srt(transcript, path)
        assert result == path
        content = open(path, encoding="utf-8").read()
        assert "Hello world" in content
        assert "This is a test" in content
        assert "00:00:00,000 --> 00:00:02,500" in content
    finally:
        os.unlink(path)


def test_transcript_to_srt_empty():
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
        path = f.name
    try:
        result = transcript_to_srt([], path)
        assert result is None
    finally:
        os.unlink(path)


def test_adjust_srt_timing():
    transcript = [
        {"start": 5.0, "end": 7.5, "text": "Trimmed start"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
        path = f.name

    try:
        transcript_to_srt(transcript, path)
        adjust_srt_timing(path, offset_seconds=5.0)
        content = open(path, encoding="utf-8").read()
        # After adjusting by -5s: 5.0 → 0.0, 7.5 → 2.5
        assert "00:00:00,000 --> 00:00:02,500" in content
    finally:
        os.unlink(path)
