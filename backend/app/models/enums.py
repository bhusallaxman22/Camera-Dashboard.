from __future__ import annotations

from enum import StrEnum


class MediaType(StrEnum):
    STILL = "still"
    VIDEO = "video"


class FileType(StrEnum):
    JPEG = "jpeg"
    IMAGE = "image"  # HEIF/PNG/TIFF: display images that can pair with a RAW
    RAW = "raw"
    VIDEO = "video"


class Flag(StrEnum):
    NONE = "none"
    PICK = "pick"
    REJECT = "reject"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    ERROR = "error"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRIED = "retried"  # failed, then superseded by a new job


class JobKind(StrEnum):
    INGEST_FILE = "ingest_file"
    RENDER = "render"
    ANALYZE = "analyze"
    AI_CRITIQUE = "ai_critique"
    SCAN = "scan"
    VERIFY = "verify"


class RenditionKind(StrEnum):
    PREVIEW = "preview"

    @staticmethod
    def thumb(size: int) -> str:
        return f"thumb_{size}"
