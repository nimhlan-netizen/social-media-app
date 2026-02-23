import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcript_to_srt(transcript: list[dict], output_path: str) -> str:
    """
    Convert Gemini transcript segments to SRT subtitle file.

    transcript: [{"start": 0.0, "end": 2.5, "text": "some words"}, ...]
    Returns path to the written .srt file.
    """
    if not transcript:
        logger.warning("Empty transcript — no SRT file generated")
        return None

    srt_lines = []
    for i, segment in enumerate(transcript, start=1):
        start = float(segment.get("start", 0))
        end = float(segment.get("end", start + 2))
        text = segment.get("text", "").strip()

        if not text:
            continue

        # Ensure end > start
        if end <= start:
            end = start + 1.5

        srt_lines.append(str(i))
        srt_lines.append(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")
        srt_lines.append(text)
        srt_lines.append("")  # blank line between entries

    srt_content = "\n".join(srt_lines)

    path = Path(output_path)
    path.write_text(srt_content, encoding="utf-8")
    logger.info(f"SRT file written to {output_path} ({len(transcript)} segments)")
    return output_path


def adjust_srt_timing(srt_path: str, offset_seconds: float) -> str:
    """
    Shift all SRT timestamps by offset_seconds (used when video is trimmed).
    Modifies the file in-place and returns the path.
    """
    if offset_seconds == 0:
        return srt_path

    path = Path(srt_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = []

    for line in lines:
        if " --> " in line:
            parts = line.split(" --> ")
            start = _srt_to_seconds(parts[0]) - offset_seconds
            end = _srt_to_seconds(parts[1]) - offset_seconds
            start = max(0.0, start)
            end = max(0.0, end)
            new_lines.append(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")
        else:
            new_lines.append(line)

    path.write_text("\n".join(new_lines), encoding="utf-8")
    return srt_path


def _srt_to_seconds(ts: str) -> float:
    """Parse SRT timestamp to seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
