import logging
import logging.config
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.config import settings
from app.models import get_engine
from app.api.routes import router

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Scheduler ────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings.ensure_dirs()
    get_engine()  # initialise DB + create tables
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Watching Drive folder: {settings.google_drive_folder_id}")

    from app.pipeline import run_pipeline

    scheduler.add_job(
        run_pipeline,
        "interval",
        seconds=settings.poll_interval_seconds,
        id="drive_poll",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        f"Scheduler started — polling Drive every {settings.poll_interval_seconds}s"
    )

    yield  # app is running

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Social Media Video Pipeline",
    description=(
        "Watches Google Drive for new video clips, analyzes with Gemini, "
        "edits with FFmpeg, and posts to social media via Postiz."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
