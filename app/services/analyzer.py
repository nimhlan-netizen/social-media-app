"""Gemini video analysis service.

Uploads the downloaded video to Gemini Files API (required for video input),
then prompts Gemini to return a structured JSON AnalysisResult containing:
  - trim_start_sec / trim_end_sec  — ideal clip window
  - hook_text                      — punchy all-caps overlay text for the first 3s
  - caption_style                  — "bold" | "minimal"
  - transcript                     — word-level timestamps [{start, end, text}, ...]
  - suggested_caption              — social media caption (no hashtags)
  - hashtags                       — list of relevant tags (no # prefix)
  - raw_duration_sec               — total video duration

The uploaded file is deleted from Gemini after analysis to avoid storage buildup.
"""
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    trim_start_sec: float
    trim_end_sec: float
    hook_text: str
    caption_style: str  # "bold" | "minimal"
    transcript: list[dict]  # [{"start": 0.0, "end": 2.5, "text": "..."}, ...]
    suggested_caption: str
    hashtags: list[str]
    raw_duration_sec: float


ANALYSIS_PROMPT = """You are a social media video editor AI. Analyze this video clip intended for Instagram Reels, Facebook Reels, and YouTube Shorts (9:16 format).

Return ONLY a valid JSON object with these exact fields:

{
  "trim_start_sec": <float, best start time to cut to - grab the most engaging moment or strongest opening>,
  "trim_end_sec": <float, best end time - aim for 15-60 seconds total, never exceed 90s>,
  "hook_text": <string, a punchy 1-line hook text to overlay at the start (max 8 words, all caps, no punctuation except ! or ?>),
  "caption_style": <"bold" or "minimal">,
  "transcript": [
    {"start": <float seconds>, "end": <float seconds>, "text": <string, spoken words in this segment>}
  ],
  "suggested_caption": <string, engaging social media caption 1-3 sentences, no hashtags>,
  "hashtags": [<string>, ...],
  "raw_duration_sec": <float, total video duration>
}

Rules:
- transcript segments should be 3-6 words each for readability as captions
- hashtags: 10-15 relevant ones, no # prefix
- hook_text should create curiosity or urgency
- trim for maximum viewer retention - cut slow intros and outros
- caption should match the video's energy and topic
"""


def analyze_video(local_path: str) -> AnalysisResult:
    """Upload video to Gemini and get structured analysis."""
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    logger.info(f"Uploading {local_path} to Gemini Files API...")
    video_file = genai.upload_file(local_path, mime_type="video/mp4")

    # Wait for file to be processed
    while video_file.state.name == "PROCESSING":
        logger.info("Gemini processing video...")
        time.sleep(3)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError(f"Gemini file processing failed for {local_path}")

    logger.info("Sending analysis prompt to Gemini...")
    response = model.generate_content(
        [video_file, ANALYSIS_PROMPT],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    # Clean up the uploaded file from Gemini
    try:
        genai.delete_file(video_file.name)
    except Exception:
        pass

    raw = response.text.strip()
    logger.info(f"Gemini response received ({len(raw)} chars)")

    data = json.loads(raw)

    # Validate and clamp values
    duration = float(data.get("raw_duration_sec", 999))
    trim_start = max(0.0, float(data.get("trim_start_sec", 0)))
    trim_end = min(duration, float(data.get("trim_end_sec", duration)))

    # Ensure minimum clip length
    if trim_end - trim_start < 5:
        trim_start = 0.0
        trim_end = min(duration, 60.0)

    return AnalysisResult(
        trim_start_sec=trim_start,
        trim_end_sec=trim_end,
        hook_text=data.get("hook_text", "WATCH THIS"),
        caption_style=data.get("caption_style", "bold"),
        transcript=data.get("transcript", []),
        suggested_caption=data.get("suggested_caption", ""),
        hashtags=data.get("hashtags", []),
        raw_duration_sec=duration,
    )
