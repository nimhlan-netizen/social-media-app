import logging
import os
import subprocess
from pathlib import Path

from app.config import settings
from app.services.analyzer import AnalysisResult

logger = logging.getLogger(__name__)


def _escape_ffmpeg_text(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    return (
        text.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace(",", "\\,")
            .replace("[", "\\[")
            .replace("]", "\\]")
    )


def edit_video(
    input_path: str,
    analysis: AnalysisResult,
    srt_path: str,
    output_path: str,
) -> str:
    """
    Run the full FFmpeg editing pipeline:
    1. Trim to analysis.trim_start_sec – trim_end_sec
    2. Burn in subtitles from srt_path
    3. Overlay hook text for first 3 seconds
    4. Re-encode H.264/AAC for platform compatibility

    Returns path to the output file.
    """
    trim_start = analysis.trim_start_sec
    trim_duration = analysis.trim_end_sec - analysis.trim_start_sec

    hook_text = _escape_ffmpeg_text(analysis.hook_text)
    srt_path_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    # Caption style
    if analysis.caption_style == "bold":
        subtitle_style = (
            "Fontname=Arial,Fontsize=14,Bold=1,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2,"
            "Alignment=2,MarginV=40"
        )
    else:
        subtitle_style = (
            "Fontname=Arial,Fontsize=12,Bold=0,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=1,"
            "Alignment=2,MarginV=40"
        )

    # Build FFmpeg filter chain
    # Layer 1: subtitles (burned in)
    # Layer 2: hook text overlay (first 3 seconds, top-center)
    subtitle_filter = f"subtitles='{srt_path_escaped}':force_style='{subtitle_style}'"

    hook_filter = (
        f"drawtext=text='{hook_text}':"
        f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"fontsize=48:fontcolor=white:borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y=h*0.12:"
        f"enable='between(t,0,3)'"
    )

    # Only add subtitle filter if SRT exists and has content
    if srt_path and Path(srt_path).exists() and Path(srt_path).stat().st_size > 10:
        video_filter = f"{subtitle_filter},{hook_filter}"
    else:
        video_filter = hook_filter

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(trim_start),
        "-t", str(trim_duration),
        "-i", input_path,
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    logger.info(f"Running FFmpeg: trim {trim_start:.1f}s to {analysis.trim_end_sec:.1f}s")
    logger.debug(f"FFmpeg command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        logger.error(f"FFmpeg stderr: {result.stderr[-2000:]}")
        raise RuntimeError(f"FFmpeg failed (code {result.returncode}): {result.stderr[-500:]}")

    output_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"FFmpeg complete. Output: {output_path} ({output_size_mb:.1f} MB)")

    # If output is too large, re-encode with lower quality
    if output_size_mb > settings.max_output_size_mb:
        logger.warning(f"Output {output_size_mb:.1f}MB exceeds limit, re-encoding...")
        output_path = _compress_video(output_path, settings.max_output_size_mb)

    return output_path


def _compress_video(input_path: str, max_mb: int) -> str:
    """Re-encode video to hit a target file size."""
    compressed_path = input_path.replace(".mp4", "_compressed.mp4")
    duration = _get_duration(input_path)
    target_bitrate = int((max_mb * 8 * 1024) / duration)  # kbps

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-b:v", f"{target_bitrate}k",
        "-maxrate", f"{target_bitrate}k",
        "-bufsize", f"{target_bitrate * 2}k",
        "-c:a", "aac", "-b:a", "96k",
        compressed_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=300)
    os.remove(input_path)
    return compressed_path


def _get_duration(path: str) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())
