from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.photo import PhotoSummary


class ComponentHealth(BaseModel):
    ok: bool
    detail: str | None = None
    data: dict[str, Any] = {}


class HealthOut(BaseModel):
    status: str
    version: str
    time: datetime
    components: dict[str, ComponentHealth]


class CameraStatus(BaseModel):
    state: str  # receiving | idle | never
    last_upload_at: datetime | None
    session_started_at: datetime | None
    session_files: int
    session_photos: int
    session_bytes: int
    camera: str | None


class TodayStats(BaseModel):
    photos: int
    raw_files: int
    jpeg_files: int
    videos: int
    bytes: int
    picks: int
    rejects: int


class TotalStats(BaseModel):
    photos: int
    raw_files: int
    jpeg_files: int
    videos: int
    bytes: int
    favorites: int
    rejected: int
    pending: int
    errors: int


class StatsOut(BaseModel):
    camera: CameraStatus
    today: TodayStats
    totals: TotalStats
    latest_photo_id: uuid.UUID | None
    recent: list[PhotoSummary]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    queue: str
    photo_id: uuid.UUID | None
    target_path: str | None
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class JobPage(BaseModel):
    items: list[JobOut]
    total: int
    counts: dict[str, int]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    level: str
    category: str
    event: str
    message: str
    photo_id: uuid.UUID | None
    data: dict[str, Any]


class AlbumIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    photo_ids: list[uuid.UUID] = []


class AlbumPhotosIn(BaseModel):
    photo_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=1000)


class AlbumOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    photo_count: int
    cover_thumb_url: str | None
    created_at: datetime
    updated_at: datetime


class TagIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    color: str | None = Field(None, max_length=16)
