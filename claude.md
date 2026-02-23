# Social Media Video Pipeline — Project Context

## What This Project Does

A self-contained Python service that:
1. **Watches** a specific Google Drive folder for new short-form video clips (9:16 MP4/MOV)
2. **Analyzes** each clip with Gemini 1.5 Flash (transcript, trim points, hook text, caption style)
3. **Edits** the clip with FFmpeg (trim + burned-in subtitles + text hook overlay)
4. **Posts** the edited clip to Instagram, Facebook, and YouTube via Postiz API

## Architecture

```
Google Drive Folder
       ↓ poll every 60s
  Drive Watcher
       ↓ download
  Gemini Analyzer  →  AnalysisResult (trim, hook, transcript, caption, hashtags)
       ↓
  Caption Generator  →  .srt file
       ↓
  FFmpeg Editor  →  edited .mp4
       ↓
  Postiz Client  →  Instagram / Facebook / YouTube
       ↓
  SQLite (VideoJob status tracking)
```

## Key Files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app + APScheduler setup |
| `app/config.py` | All settings via Pydantic + .env |
| `app/models.py` | SQLite schema (VideoJob) |
| `app/pipeline.py` | Main orchestrator (download→analyze→edit→post) |
| `app/services/drive_watcher.py` | Google Drive API polling |
| `app/services/analyzer.py` | Gemini 1.5 Flash video analysis |
| `app/services/caption_generator.py` | Transcript → SRT conversion |
| `app/services/editor.py` | FFmpeg editing pipeline |
| `app/services/postiz_client.py` | Postiz REST API client |
| `app/api/routes.py` | FastAPI routes (health, jobs, retry, trigger) |

## Environment Variables

All secrets live in `.env` (never committed). See `.env.example` for the full list.

Required:
- `GOOGLE_DRIVE_FOLDER_ID` — ID from Drive folder URL
- `GOOGLE_SERVICE_ACCOUNT_JSON` — Path to service account key JSON
- `GEMINI_API_KEY` — Google AI Studio API key
- `POSTIZ_API_URL` — https://postiz.almostrolledit.com
- `POSTIZ_API_KEY` — From Postiz settings panel

## Tech Stack

- **Python 3.12** — language
- **FastAPI + Uvicorn** — web framework
- **APScheduler** — background job scheduling (polls Drive every 60s)
- **SQLModel + SQLite** — job state tracking
- **google-api-python-client** — Drive API
- **google-generativeai** — Gemini API
- **ffmpeg-python** — FFmpeg wrapper
- **httpx** — async HTTP client for Postiz
- **Docker** — deployed on Coolify VPS

## Data Flow Details

### VideoJob Statuses
`pending` → `downloading` → `analyzing` → `editing` → `posting` → `done` | `failed`

### FFmpeg Pipeline (single pass)
1. Trim to `trim_start_sec` – `trim_end_sec` from Gemini analysis
2. Burn in `.srt` subtitles (white text, black outline, bottom-center)
3. Overlay hook text for first 3 seconds (top-center, large bold)
4. Re-encode: H.264 video, AAC audio, CRF 23, 9:16 aspect preserved
5. Output ~15MB max for Instagram compatibility

### Postiz Integration
- Upload video to Postiz media endpoint first
- Create a single post targeting all 3 platforms simultaneously
- Caption = Gemini `suggested_caption` + `\n\n` + `hashtags`

## Development Notes

- FFmpeg must be installed in the container (`apt-get install ffmpeg`)
- Service account must be shared on the watched Drive folder
- All temp files written to `DATA_DIR` (default: `/data` in Docker, `./data` locally)
- The `/trigger` endpoint is useful for manual testing without waiting for the poll interval
- Failed jobs can be retried via `POST /jobs/{job_id}/retry`

## Adding New Features

- **New platform**: Add a new method to `postiz_client.py` and call it from `pipeline.py`
- **New overlay type**: Add to `editor.py` FFmpeg filter chain
- **New analysis field**: Add to `AnalysisResult` in `analyzer.py`, update the Gemini prompt
