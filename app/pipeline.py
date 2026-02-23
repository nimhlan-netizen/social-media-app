"""Pipeline orchestrator for the Social Media Video Pipeline.

This module is the main entry point called by the APScheduler every `POLL_INTERVAL_SECONDS`.
For each new file found in Google Drive, it runs the full processing chain:

    download → analyze (Gemini) → generate captions (SRT) → edit (FFmpeg) → post (Postiz)

Each step updates the VideoJob.status in SQLite so progress is always visible via /jobs.
On any exception the job is marked `failed` with the error message stored for debugging.
Failed jobs can be retried via the /jobs/{id}/retry API endpoint.
"""
import logging
from pathlib import Path

from app.config import settings
from app.models import VideoJob, save_job, get_job_by_drive_id
from app.services.drive_watcher import list_new_files, create_and_download_job
from app.services.analyzer import analyze_video
from app.services.caption_generator import transcript_to_srt, adjust_srt_timing
from app.services.editor import edit_video
from app.services.postiz_client import PostizClient

logger = logging.getLogger(__name__)


def _update_status(job: VideoJob, status: str, error: str = None):
    job.set_status(status, error)
    save_job(job)


def process_job(job: VideoJob):
    """Run the full pipeline for a single VideoJob."""
    logger.info(f"[Pipeline] Starting job {job.id}: {job.file_name}")

    try:
        # === ANALYZE ===
        _update_status(job, "analyzing")
        analysis = analyze_video(job.local_path)
        logger.info(
            f"[Pipeline] Analysis complete: trim {analysis.trim_start_sec:.1f}s–{analysis.trim_end_sec:.1f}s, "
            f"hook='{analysis.hook_text}'"
        )

        # Store analysis results on the job
        job.suggested_caption = analysis.suggested_caption
        job.hashtags = ",".join(analysis.hashtags)
        job.hook_text = analysis.hook_text
        save_job(job)

        # === GENERATE CAPTIONS ===
        stem = Path(job.file_name).stem
        srt_path = str(settings.captions_dir / f"{stem}.srt")

        if analysis.transcript:
            # Adjust transcript timing to account for trim offset
            adjusted_transcript = []
            for seg in analysis.transcript:
                new_start = float(seg["start"]) - analysis.trim_start_sec
                new_end = float(seg["end"]) - analysis.trim_start_sec
                if new_end > 0:  # skip segments before trim start
                    adjusted_transcript.append({
                        "start": max(0.0, new_start),
                        "end": max(0.0, new_end),
                        "text": seg["text"],
                    })
            srt_result = transcript_to_srt(adjusted_transcript, srt_path)
        else:
            srt_result = None

        job.captions_path = srt_result
        save_job(job)

        # === EDIT ===
        _update_status(job, "editing")
        output_path = str(settings.output_dir / f"{stem}_edited.mp4")
        edited_path = edit_video(
            input_path=job.local_path,
            analysis=analysis,
            srt_path=srt_result,
            output_path=output_path,
        )
        job.output_path = edited_path
        save_job(job)
        logger.info(f"[Pipeline] Video edited: {edited_path}")

        # === POST ===
        _update_status(job, "posting")
        client = PostizClient()
        post_id = client.post_video(
            file_path=edited_path,
            caption=analysis.suggested_caption,
            hashtags=analysis.hashtags,
        )
        job.postiz_post_id = post_id
        _update_status(job, "done")
        logger.info(f"[Pipeline] Job {job.id} complete. Postiz post ID: {post_id}")

    except Exception as e:
        logger.exception(f"[Pipeline] Job {job.id} failed: {e}")
        _update_status(job, "failed", error=str(e))


def run_pipeline():
    """Main pipeline entry point. Called by the APScheduler every poll interval."""
    logger.info("[Pipeline] Scanning Google Drive for new files...")
    try:
        new_files = list_new_files()
    except Exception as e:
        logger.error(f"[Pipeline] Drive scan failed: {e}")
        return

    if not new_files:
        logger.debug("[Pipeline] No new files found.")
        return

    logger.info(f"[Pipeline] Found {len(new_files)} new file(s) to process.")
    for drive_file in new_files:
        try:
            job = create_and_download_job(drive_file)
            process_job(job)
        except Exception as e:
            logger.error(f"[Pipeline] Failed to process {drive_file['name']}: {e}")


def retry_job(job_id: int) -> bool:
    """Retry a failed job by job ID. Returns True if job was found and retried."""
    from app.models import get_job_by_id
    job = get_job_by_id(job_id)
    if not job:
        return False
    if job.status not in ("failed",):
        return False

    logger.info(f"[Pipeline] Retrying job {job_id}: {job.file_name}")
    job.error = None
    if not job.local_path or not Path(job.local_path).exists():
        # Need to re-download
        _update_status(job, "downloading")
        from app.services.drive_watcher import download_file
        local_path = download_file(job.drive_file_id, job.file_name)
        job.local_path = local_path
        _update_status(job, "downloaded")

    process_job(job)
    return True
