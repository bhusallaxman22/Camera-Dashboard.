from __future__ import annotations

import base64
import io
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass(slots=True)
class PhotoContext:
    """Everything a provider may use about a photo (no ORM objects leak out)."""

    photo_id: str
    filename: str
    camera: str | None = None
    lens: str | None = None
    focal_length: float | None = None
    focal_length_35mm: float | None = None
    aperture: float | None = None
    shutter_speed: float | None = None
    iso: int | None = None
    exposure_compensation: float | None = None
    exposure_program: str | None = None
    focus_mode: str | None = None
    af_area_mode: str | None = None
    vibration_reduction: str | None = None
    subject_detection: str | None = None
    focus_distance: str | None = None
    capture_time: str | None = None
    technical: dict[str, Any] = field(default_factory=dict)

    def summary_lines(self) -> list[str]:
        from app.utils.format import format_ev, format_shutter

        lines = [f"File: {self.filename}"]
        if self.camera:
            lines.append(f"Camera: {self.camera}")
        if self.lens:
            lines.append(f"Lens: {self.lens}")
        exp = [
            f"{self.focal_length:g}mm" if self.focal_length else None,
            f"f/{self.aperture:g}" if self.aperture else None,
            format_shutter(self.shutter_speed),
            f"ISO {self.iso}" if self.iso else None,
            format_ev(self.exposure_compensation),
        ]
        if any(exp):
            lines.append("Exposure: " + ", ".join(e for e in exp if e))
        for label, value in (
            ("Mode", self.exposure_program),
            ("Focus", self.focus_mode),
            ("AF area", self.af_area_mode),
            ("Subject detection", self.subject_detection),
            ("VR", self.vibration_reduction),
            ("Focus distance", self.focus_distance),
        ):
            if value:
                lines.append(f"{label}: {value}")
        t = self.technical
        if t:
            lines.append(
                "Measured (from JPEG rendering): "
                f"sharpness {t.get('sharpness_score')}/100 ({t.get('sharpness_label')}), "
                f"brightness {t.get('brightness')}, highlights clipped "
                f"{t.get('highlight_clipping_percent')}%, shadows clipped "
                f"{t.get('shadow_clipping_percent')}%, faces {t.get('face_count')}"
            )
        return lines


@dataclass(slots=True)
class AIResult:
    scene: str | None = None
    subject: str | None = None
    description: str | None = None
    composition: list[str] = field(default_factory=list)
    technical: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    aesthetic_score: float | None = None
    confidence: float | None = None
    model_name: str | None = None
    model_version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIProviderError(RuntimeError):
    pass


class AIProvider(ABC):
    """Interface every analysis provider implements."""

    name: str = "base"

    @abstractmethod
    def analyze_photo(self, photo: PhotoContext, preview: Path) -> AIResult:
        """Analyse one photo given its metadata and a browser-sized preview JPEG."""

    def is_configured(self) -> bool:
        return True

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "configured": self.is_configured()}


# JSON schema shared by remote providers (OpenAI structured outputs / Ollama format).
CRITIQUE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scene": {
            "type": "string",
            "description": "short scene category, e.g. portrait, landscape, street, wildlife, macro, night, sports, architecture, event, product",
        },
        "subject": {"type": "string"},
        "description": {"type": "string", "description": "1-2 sentence description of the image"},
        "composition": {"type": "array", "items": {"type": "string"}},
        "technical": {"type": "array", "items": {"type": "string"}},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "aesthetic_score": {"type": "number", "description": "0-10 subjective aesthetic estimate"},
        "confidence": {"type": "number", "description": "0-1 confidence in this critique"},
    },
    "required": [
        "scene",
        "subject",
        "description",
        "composition",
        "technical",
        "issues",
        "suggestions",
        "tags",
        "aesthetic_score",
        "confidence",
    ],
}

SYSTEM_PROMPT = (
    "You are an experienced photography mentor reviewing a single frame shot on a Nikon "
    "mirrorless camera. Be specific, practical and honest but kind. Base technical comments "
    "on the provided EXIF and measurements as well as what you see. Phrase uncertain "
    "observations as likely/possible. Suggestions should be actionable for the next shot "
    "(e.g. exposure compensation in 1/3 EV steps, shutter speed, aperture, AF mode, "
    "composition). Respond only with JSON matching the schema."
)


def encode_preview(preview: Path, max_edge: int = 1024, quality: int = 85) -> str:
    with Image.open(preview) as im:
        im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def result_from_json(data: dict[str, Any], model_name: str | None) -> AIResult:
    def _list(key: str) -> list[str]:
        v = data.get(key) or []
        return [str(x) for x in v][:12] if isinstance(v, list) else [str(v)]

    def _num(key: str, lo: float, hi: float) -> float | None:
        try:
            return max(lo, min(hi, float(data[key])))
        except (KeyError, TypeError, ValueError):
            return None

    return AIResult(
        scene=(str(data.get("scene") or "").strip().lower() or None),
        subject=data.get("subject") or None,
        description=data.get("description") or None,
        composition=_list("composition"),
        technical=_list("technical"),
        issues=_list("issues"),
        suggestions=_list("suggestions"),
        tags=[t.lower() for t in _list("tags")],
        aesthetic_score=_num("aesthetic_score", 0, 10),
        confidence=_num("confidence", 0, 1),
        model_name=model_name,
    )
