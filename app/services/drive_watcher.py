import json
import logging
import os
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from app.config import settings
from app.models import VideoJob, get_job_by_drive_id, save_job
import io

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _get_drive_service():
    # Prefer inline JSON content (set as env var in Coolify/Docker)
    if settings.google_service_account_json_content:
        info = json.loads(settings.google_service_account_json_content)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Fall back to file path (local development)
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json, scopes=SCOPES
        )
    return build("drive", "v3", credentials=creds)


def list_new_files() -> list[dict]:
    """Return files from the watched folder that haven't been processed yet."""
    service = _get_drive_service()
    query = f"'{settings.google_drive_folder_id}' in parents and trashed=false"
    fields = "files(id, name, mimeType, createdTime, size)"

    result = service.files().list(
        q=query,
        fields=fields,
        orderBy="createdTime desc",
        pageSize=50,
    ).execute()

    files = result.get("files", [])
    new_files = []

    for f in files:
        ext = Path(f["name"]).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        existing = get_job_by_drive_id(f["id"])
        if existing is None:
            new_files.append(f)
            logger.info(f"New file detected: {f['name']} ({f['id']})")

    return new_files


def download_file(file_id: str, file_name: str) -> str:
    """Download a Drive file to the local downloads directory. Returns local path."""
    service = _get_drive_service()
    dest = settings.downloads_dir / file_name

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(str(dest), "wb")
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            logger.info(f"Download {file_name}: {int(status.progress() * 100)}%")

    fh.close()
    logger.info(f"Downloaded {file_name} to {dest}")
    return str(dest)


def create_and_download_job(drive_file: dict) -> VideoJob:
    """Create a VideoJob record and download the file. Returns the job."""
    job = VideoJob(
        drive_file_id=drive_file["id"],
        file_name=drive_file["name"],
        status="downloading",
    )
    save_job(job)

    local_path = download_file(drive_file["id"], drive_file["name"])
    job.local_path = local_path
    job.status = "downloaded"
    save_job(job)
    return job
