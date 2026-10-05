from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, validated from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Z6III AI Studio"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg://z6iii:z6iii@localhost:5432/z6iii"
    redis_url: str = "redis://localhost:6379/0"

    photo_root: Path = Path("/photos")
    jpeg_root: Path = Path("/photos/immich-jpeg")
    raw_root: Path = Path("/photos/raw")
    video_root: Path = Path("/photos/video")
    # The sorter files extensions it does not know (e.g. Nikon HEIF `.HIF`) here.
    # Optional: may not exist yet; set to an empty value to stop watching it.
    unsorted_root: Path | None = Path("/photos/unsorted")
    data_root: Path = Path("/data")
    thumbnail_root: Path = Path("/data/thumbnails")
    preview_root: Path = Path("/data/previews")
    cache_root: Path = Path("/data/cache")

    nas_photo_root: str = "/mnt/mainpool/photos/z6iii"
    smb_photo_root: str = ""

    watch_enabled: bool = True
    watch_mode: Literal["auto", "inotify", "polling"] = "auto"
    watch_poll_interval_seconds: float = 2.0
    file_stable_seconds: float = Field(3.0, ge=0.5)
    scan_on_startup: bool = True
    reconcile_interval_minutes: int = Field(30, ge=0)

    pair_window_seconds: float = Field(2.0, gt=0)
    burst_max_gap_seconds: float = Field(1.0, gt=0)
    burst_focal_tolerance: float = 0.05
    ingest_session_gap_minutes: int = 20
    camera_online_minutes: int = 5

    preview_max_edge: int = 2560
    preview_quality: int = Field(85, ge=40, le=100)
    thumbnail_sizes: Annotated[list[int], NoDecode] = [256, 512, 1024]
    thumbnail_quality: int = Field(80, ge=40, le=100)

    ai_provider: Literal["local", "openai", "ollama", "none"] = "local"
    ai_auto_analyze: bool = True
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_url: str = ""
    ollama_model: str = "qwen2.5vl:7b"
    ai_timeout_seconds: float = 120.0

    immich_enabled: bool = False
    immich_url: str = ""
    immich_public_url: str = ""
    immich_api_key: str = ""

    api_token: str = ""
    cors_origins: Annotated[list[str], NoDecode] = []

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    face_model_path: Path = Path("/opt/models/face_detection_yunet_2023mar.onnx")
    exiftool_path: str = "exiftool"
    ffmpeg_path: str = "ffmpeg"

    job_timeout_seconds: int = 600
    job_max_retries: int = 3

    @field_validator("thumbnail_sizes", mode="before")
    @classmethod
    def _parse_sizes(cls, v: object) -> object:
        if isinstance(v, str):
            return sorted({int(s) for s in v.split(",") if s.strip()})
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("unsorted_root", mode="before")
    @classmethod
    def _empty_root_disables(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Accept the conventional postgresql:// form and pin the psycopg3 driver.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @property
    def media_roots(self) -> dict[str, Path]:
        roots = {"jpeg": self.jpeg_root, "raw": self.raw_root, "video": self.video_root}
        if self.unsorted_root is not None:
            roots["unsorted"] = self.unsorted_root
        return roots

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def display_path(self, absolute_path: str) -> str:
        """Translate a container path (/photos/...) to the NAS path."""
        root = str(self.photo_root).rstrip("/")
        if absolute_path == root or absolute_path.startswith(root + "/"):
            return self.nas_photo_root.rstrip("/") + absolute_path[len(root) :]
        return absolute_path

    def smb_path(self, absolute_path: str) -> str | None:
        if not self.smb_photo_root:
            return None
        root = str(self.photo_root).rstrip("/")
        if not absolute_path.startswith(root + "/"):
            return None
        rel = absolute_path[len(root) + 1 :]
        share = self.smb_photo_root.strip().rstrip("\\/")
        if share.lower().startswith("smb://"):
            return share + "/" + rel
        # Accept "host\share" or "//host/share" as well as the canonical UNC form.
        share = "\\\\" + share.lstrip("\\/").replace("/", "\\")
        return share + "\\" + rel.replace("/", "\\")


@lru_cache
def get_settings() -> Settings:
    return Settings()
