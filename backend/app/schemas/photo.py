from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PhotoSummary(ORM):
    id: uuid.UUID
    base_filename: str
    media_type: str
    capture_time: datetime | None
    imported_at: datetime
    camera: str | None
    lens_model: str | None
    focal_length: float | None
    aperture: float | None
    shutter_speed: float | None
    iso: int | None
    exposure_compensation: float | None
    rating: int
    flag: str
    rejected: bool
    picked: bool
    favorite: bool
    needs_edit: bool
    exported: bool
    has_jpeg: bool
    has_raw: bool
    has_video: bool
    processing_status: str
    scene: str | None
    burst_group_id: uuid.UUID | None
    burst_index: int | None
    burst_size: int | None = None
    thumb_url: str | None
    thumb_width: int | None
    thumb_height: int | None
    sharpness_score: float | None = None
    exposure_label: str | None = None
    face_count: int | None = None


class PhotoPage(BaseModel):
    items: list[PhotoSummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class BestPhoto(BaseModel):
    photo: PhotoSummary
    score: float
    aesthetic_score: float | None
    eye_sharpness: float | None


class BestPhotos(BaseModel):
    period: str
    period_start: datetime | None
    candidates: int
    ai_scored: int
    items: list[BestPhoto]


class PhotoFileOut(ORM):
    id: uuid.UUID
    file_type: str
    filename: str
    extension: str
    mime_type: str | None
    file_size: int
    checksum: str | None
    modification_time: datetime
    width: int | None
    height: int | None
    exists: bool
    is_duplicate: bool
    container_path: str
    nas_path: str
    smb_path: str | None
    relative_path: str
    download_url: str


class AnalysisOut(ORM):
    sharpness_score: float | None
    sharpness_label: str | None
    sharpness_global: float | None
    sharpness_peak: float | None
    blur_score: float | None
    is_blurry: bool | None
    brightness: float | None
    contrast: float | None
    saturation: float | None
    dynamic_range_ev: float | None
    highlight_clipping_percent: float | None
    shadow_clipping_percent: float | None
    exposure_label: str | None
    exposure_assessment: str | None
    histogram: dict[str, list[int]]
    dominant_colors: list[dict[str, Any]]
    face_count: int | None
    eye_count: int | None
    faces: list[dict[str, Any]]
    subject_detected: bool | None
    warnings: list[str]
    source: str | None
    algorithm_version: str
    duration_ms: int | None
    analyzed_at: datetime


class CritiqueOut(ORM):
    id: uuid.UUID
    provider: str
    model_name: str | None
    status: str
    scene: str | None
    subject: str | None
    description: str | None
    composition: list[str]
    technical: list[str]
    issues: list[str]
    suggestions: list[str]
    tags: list[str]
    aesthetic_score: float | None
    confidence: float | None
    error: str | None
    duration_ms: int | None
    created_at: datetime


class TagOut(ORM):
    id: int
    name: str
    color: str | None = None
    count: int | None = None


class BurstOut(BaseModel):
    id: uuid.UUID
    photo_count: int
    start_time: datetime
    end_time: datetime
    cover_photo_id: uuid.UUID | None
    members: list[PhotoSummary]


class PhotoDetail(PhotoSummary):
    camera_make: str | None
    camera_model: str | None
    camera_serial: str | None
    shutter_count: int | None
    firmware: str | None
    capture_tz_offset: str | None
    focal_length_35mm: float | None
    exposure_program: str | None
    metering_mode: str | None
    white_balance: str | None
    flash: str | None
    focus_mode: str | None
    af_area_mode: str | None
    picture_control: str | None
    image_quality: str | None
    image_width: int | None
    image_height: int | None
    orientation: int | None
    color_space: str | None
    duration_seconds: float | None
    gps_latitude: float | None
    gps_longitude: float | None
    gps_altitude: float | None
    extra: dict[str, Any]
    notes: str | None
    processing_error: str | None
    preview_url: str | None
    preview_width: int | None
    preview_height: int | None
    files: list[PhotoFileOut]
    analysis: AnalysisOut | None
    critique: CritiqueOut | None
    critique_history: int
    tags: list[TagOut]
    albums: list[dict[str, Any]]
    burst: BurstOut | None
    immich_asset_id: str | None
    immich_url: str | None
    immich_enabled: bool = False
    prev_id: uuid.UUID | None
    next_id: uuid.UUID | None


class PhotoUpdate(BaseModel):
    rating: int | None = Field(None, ge=0, le=5)
    flag: Literal["none", "pick", "reject"] | None = None
    favorite: bool | None = None
    needs_edit: bool | None = None
    exported: bool | None = None
    notes: str | None = Field(None, max_length=10000)
    tags: list[str] | None = Field(None, max_length=50)


class BulkUpdate(PhotoUpdate):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=500)


class AnalyzeRequest(BaseModel):
    technical: bool = True
    ai: bool = True
    provider: Literal["local", "openai", "ollama"] | None = None
    rerender: bool = False


class Facets(BaseModel):
    cameras: list[str]
    lenses: list[str]
    scenes: list[str]
    tags: list[str]
    iso_range: tuple[int | None, int | None]
    focal_range: tuple[float | None, float | None]
    aperture_range: tuple[float | None, float | None]
    date_range: tuple[datetime | None, datetime | None]
