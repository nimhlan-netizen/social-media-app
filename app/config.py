from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Google Drive
    google_drive_folder_id: str
    google_service_account_json: str = "service_account.json"  # file path (local dev)
    google_service_account_json_content: str = ""  # raw JSON string (Coolify/Docker env var)

    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"

    # Postiz
    postiz_api_url: str = "https://postiz.almostrolledit.com"
    postiz_api_key: str

    # Pipeline
    poll_interval_seconds: int = 60
    data_dir: str = "./data"
    max_output_size_mb: int = 95  # Instagram limit is 100MB

    # Postiz platform integration IDs (set after connecting accounts in Postiz)
    postiz_instagram_integration_id: str = ""
    postiz_facebook_integration_id: str = ""
    postiz_youtube_integration_id: str = ""

    @property
    def downloads_dir(self) -> Path:
        return Path(self.data_dir) / "downloads"

    @property
    def output_dir(self) -> Path:
        return Path(self.data_dir) / "output"

    @property
    def captions_dir(self) -> Path:
        return Path(self.data_dir) / "captions"

    @property
    def db_path(self) -> str:
        return str(Path(self.data_dir) / "pipeline.db")

    def ensure_dirs(self):
        for d in [self.downloads_dir, self.output_dir, self.captions_dir]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
