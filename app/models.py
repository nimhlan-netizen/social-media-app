from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select
from app.config import settings


class VideoJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    drive_file_id: str = Field(index=True, unique=True)
    file_name: str
    status: str = Field(default="pending")  # pending|downloading|analyzing|editing|posting|done|failed
    error: Optional[str] = None

    # Paths
    local_path: Optional[str] = None
    output_path: Optional[str] = None
    captions_path: Optional[str] = None

    # Analysis results (stored as JSON strings)
    suggested_caption: Optional[str] = None
    hashtags: Optional[str] = None
    hook_text: Optional[str] = None

    # Postiz tracking
    postiz_post_id: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def set_status(self, status: str, error: str = None):
        self.status = status
        self.updated_at = datetime.utcnow()
        if error:
            self.error = error
        if status == "done":
            self.completed_at = datetime.utcnow()


engine = None


def get_engine():
    global engine
    if engine is None:
        engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)
        SQLModel.metadata.create_all(engine)
    return engine


def get_session():
    return Session(get_engine())


def get_job_by_drive_id(drive_file_id: str) -> Optional[VideoJob]:
    with get_session() as session:
        return session.exec(
            select(VideoJob).where(VideoJob.drive_file_id == drive_file_id)
        ).first()


def save_job(job: VideoJob):
    with get_session() as session:
        session.add(job)
        session.commit()
        session.refresh(job)
    return job


def get_all_jobs() -> list[VideoJob]:
    with get_session() as session:
        return session.exec(select(VideoJob).order_by(VideoJob.created_at.desc())).all()


def get_job_by_id(job_id: int) -> Optional[VideoJob]:
    with get_session() as session:
        return session.get(VideoJob, job_id)
