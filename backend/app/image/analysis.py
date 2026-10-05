"""Local technical image analysis (no network, no AI credentials).

All metrics are computed on the rendered preview (camera JPEG or embedded RAW
preview), so clipping reflects the JPEG rendering — the RAW usually holds more
highlight/shadow headroom. Labels are deliberately phrased as estimates.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.config import get_settings
from app.log import get_logger

log = get_logger(__name__)

ALGORITHM_VERSION = "1.0"

ANALYSIS_EDGE = 1600  # long edge used for sharpness (resolution-normalised)
FACE_EDGE = 1280
HIGHLIGHT_LEVEL = 252  # any channel at/above this is treated as clipped
SHADOW_LEVEL = 3  # luminance at/below this is treated as crushed
# Log-scale mapping of Laplacian variance to 0-100.
SHARP_LO, SHARP_HI = 15.0, 1500.0


@dataclass(slots=True)
class FaceResult:
    x: float  # normalised 0-1 box in the oriented preview
    y: float
    w: float
    h: float
    confidence: float
    sharpness: float | None = None
    eyes: list[dict[str, float]] = field(default_factory=list)


@dataclass(slots=True)
class AnalysisResult:
    sharpness_score: float
    sharpness_label: str
    sharpness_global: float
    sharpness_peak: float
    blur_score: float
    is_blurry: bool
    brightness: float
    contrast: float
    saturation: float
    dynamic_range_ev: float
    highlight_clipping_percent: float
    shadow_clipping_percent: float
    exposure_label: str
    exposure_assessment: str
    histogram: dict[str, list[int]]
    dominant_colors: list[dict[str, Any]]
    face_count: int | None
    eye_count: int | None
    faces: list[dict[str, Any]]
    subject_detected: bool
    warnings: list[str]
    analyzed_width: int
    analyzed_height: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resize_long_edge(arr: np.ndarray, edge: int) -> np.ndarray:
    h, w = arr.shape[:2]
    scale = edge / max(h, w)
    if scale >= 1:
        return arr
    return cv2.resize(arr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 luma on gamma-encoded values (0-255 float32)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return 0.2126 * r.astype(np.float32) + 0.7152 * g + 0.0722 * b


def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F, ksize=3).var())


def sharpness_metrics(gray: np.ndarray, grid: int = 8) -> tuple[float, float]:
    """(global, peak) Laplacian variance.

    Peak = mean of the sharpest 10% of tiles, so a sharp subject on a blurred
    background (shallow depth of field) still scores as sharp.
    """
    g = _resize_long_edge(gray, ANALYSIS_EDGE)
    g = cv2.GaussianBlur(g, (3, 3), 0)  # suppress sensor noise / JPEG grain
    lap = cv2.Laplacian(g, cv2.CV_64F, ksize=3)
    global_var = float(lap.var())
    h, w = lap.shape
    th, tw = max(h // grid, 1), max(w // grid, 1)
    tiles = [
        float(lap[y : y + th, x : x + tw].var()) for y in range(0, h - th + 1, th) for x in range(0, w - tw + 1, tw)
    ]
    tiles.sort(reverse=True)
    top = tiles[: max(1, len(tiles) // 10)]
    return global_var, float(np.mean(top))


def sharpness_score(peak: float) -> float:
    if peak <= 0:
        return 0.0
    v = (math.log10(peak) - math.log10(SHARP_LO)) / (math.log10(SHARP_HI) - math.log10(SHARP_LO))
    return round(max(0.0, min(1.0, v)) * 100, 1)


def sharpness_label(score: float) -> str:
    if score >= 75:
        return "Excellent"
    if score >= 55:
        return "Good"
    if score >= 35:
        return "Acceptable"
    if score >= 20:
        return "Soft"
    return "Likely blurry"


def histograms(rgb: np.ndarray, lum: np.ndarray) -> dict[str, list[int]]:
    out = {c: np.bincount(rgb[..., i].ravel(), minlength=256).astype(int).tolist() for i, c in enumerate("rgb")}
    out["l"] = np.bincount(np.clip(lum, 0, 255).astype(np.uint8).ravel(), minlength=256).astype(int).tolist()
    return out


def clipping(rgb: np.ndarray, lum: np.ndarray) -> tuple[float, float]:
    total = lum.size
    highlights = np.count_nonzero(rgb.max(axis=2) >= HIGHLIGHT_LEVEL) / total * 100
    shadows = np.count_nonzero(lum <= SHADOW_LEVEL) / total * 100
    return round(float(highlights), 2), round(float(shadows), 2)


def _srgb_to_linear(v: float) -> float:
    c = v / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def dynamic_range_ev(lum: np.ndarray) -> float:
    """Approximate scene range in stops between the 0.5th and 99.5th luma percentiles."""
    lo, hi = np.percentile(lum, [0.5, 99.5])
    lin_lo = max(_srgb_to_linear(float(lo)), 1 / 4096)
    lin_hi = max(_srgb_to_linear(float(hi)), lin_lo)
    return round(math.log2(lin_hi / lin_lo), 2)


def dominant_colors(rgb: np.ndarray, k: int = 5) -> list[dict[str, Any]]:
    small = cv2.resize(rgb, (64, 64), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(42)
    _, labels, centers = cv2.kmeans(small, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    order = np.argsort(-counts)
    return [
        {
            "hex": "#{:02x}{:02x}{:02x}".format(*(int(c) for c in centers[i])),
            "fraction": round(float(counts[i] / counts.sum()), 3),
        }
        for i in order
    ]


def assess_exposure(brightness: float, hi_clip: float, lo_clip: float) -> tuple[str, str]:
    """(label, sentence). Heuristic; may misread intentional low/high-key work."""
    if hi_clip > 2.0 and lo_clip > 2.0:
        return "high_contrast", (
            f"High contrast: about {hi_clip:.1f}% highlights and {lo_clip:.1f}% shadows clipped in the JPEG rendering."
        )
    if brightness < 0.22 and lo_clip > 4.0:
        return "under", "Likely underexposed: dark histogram with crushed shadows."
    if brightness > 0.62 and hi_clip > 4.0:
        return "over", "Likely overexposed: bright histogram with clipped highlights."
    if hi_clip > 1.5:
        return "good_hi_clip", f"Exposure looks reasonable, but ~{hi_clip:.1f}% of highlights are clipped."
    if brightness < 0.25:
        return "low_key", "Dark / low-key image (may be intentional)."
    if brightness > 0.72:
        return "high_key", "Bright / high-key image (may be intentional)."
    return "good", "Exposure looks balanced."


@lru_cache(maxsize=4)
def _face_detector(model_path: str, w: int, h: int) -> Any:
    det = cv2.FaceDetectorYN.create(model_path, "", (w, h), 0.75, 0.3, 50)
    return det


def detect_faces(rgb: np.ndarray, gray_full: np.ndarray) -> list[FaceResult] | None:
    """YuNet faces with eye landmarks. Returns None if the model is unavailable."""
    model = get_settings().face_model_path
    if not Path(model).exists():
        return None
    small = _resize_long_edge(rgb, FACE_EDGE)
    h, w = small.shape[:2]
    try:
        det = _face_detector(str(model), w, h)
        det.setInputSize((w, h))
        _, faces = det.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    except cv2.error as exc:
        log.warning("face_detection_failed", category="ANALYSIS", error=str(exc))
        return None
    if faces is None:
        return []
    gh, gw = gray_full.shape[:2]
    sx, sy = gw / w, gh / h
    results: list[FaceResult] = []
    min_side = 0.02 * min(w, h)
    for f in faces:
        x, y, fw, fh = (float(v) for v in f[:4])
        if fw < min_side or fh < min_side:
            continue
        conf = float(f[14])
        # Landmarks: right eye (4,5), left eye (6,7) in image coordinates.
        eyes = []
        eye_radius = max(4, int(fw * 0.12 * sx))
        for ex, ey in ((f[4], f[5]), (f[6], f[7])):
            cx, cy = int(ex * sx), int(ey * sy)
            patch = gray_full[max(cy - eye_radius, 0) : cy + eye_radius, max(cx - eye_radius, 0) : cx + eye_radius]
            eye_sharp = laplacian_variance(patch) if patch.size > 16 else None
            eyes.append(
                {
                    "x": round(float(ex) / w, 4),
                    "y": round(float(ey) / h, 4),
                    "sharpness": round(sharpness_score(eye_sharp), 1) if eye_sharp else None,
                }
            )
        x0, y0 = int(x * sx), int(y * sy)
        roi = gray_full[max(y0, 0) : y0 + int(fh * sy), max(x0, 0) : x0 + int(fw * sx)]
        face_sharp = sharpness_score(laplacian_variance(roi)) if roi.size > 64 else None
        results.append(
            FaceResult(
                x=round(x / w, 4),
                y=round(y / h, 4),
                w=round(fw / w, 4),
                h=round(fh / h, 4),
                confidence=round(conf, 3),
                sharpness=face_sharp,
                eyes=eyes,
            )
        )
    return results


def analyze_image(img: Image.Image) -> AnalysisResult:
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    lum = luminance(rgb)
    gray = np.clip(lum, 0, 255).astype(np.uint8)

    g_var, peak = sharpness_metrics(gray)
    score = sharpness_score(peak)
    hi, lo = clipping(rgb, lum)
    brightness = round(float(lum.mean() / 255), 4)
    contrast = round(float(lum.std() / 255), 4)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    saturation = round(float(hsv[..., 1].mean() / 255), 4)
    exp_label, exp_text = assess_exposure(brightness, hi, lo)

    faces = detect_faces(rgb, gray)
    face_count = None if faces is None else len(faces)
    eye_count = None if faces is None else sum(len(f.eyes) for f in faces)

    warnings: list[str] = []
    if score < 25:
        warnings.append("Image is likely blurry (missed focus or motion blur).")
    if hi > 3:
        warnings.append(f"{hi:.1f}% of pixels have a clipped channel in the JPEG rendering.")
    if lo > 5:
        warnings.append(f"{lo:.1f}% of pixels are crushed to black.")
    if faces:
        soft_eyes = [e for f in faces for e in f.eyes if e["sharpness"] is not None and e["sharpness"] < 30]
        if soft_eyes and len(soft_eyes) == sum(len(f.eyes) for f in faces):
            warnings.append("Detected eyes appear soft; focus may have missed the eyes.")

    # Subject heuristic: faces, or a markedly sharper region than the frame average.
    subject = bool(faces) or (g_var > 0 and peak / g_var > 2.5 and score >= 45)

    return AnalysisResult(
        sharpness_score=score,
        sharpness_label=sharpness_label(score),
        sharpness_global=round(g_var, 2),
        sharpness_peak=round(peak, 2),
        blur_score=round(1 - score / 100, 3),
        is_blurry=score < 25,
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        dynamic_range_ev=dynamic_range_ev(lum),
        highlight_clipping_percent=hi,
        shadow_clipping_percent=lo,
        exposure_label=exp_label,
        exposure_assessment=exp_text,
        histogram=histograms(rgb, lum),
        dominant_colors=dominant_colors(rgb),
        face_count=face_count,
        eye_count=eye_count,
        faces=[asdict(f) for f in faces or []],
        subject_detected=subject,
        warnings=warnings,
        analyzed_width=w,
        analyzed_height=h,
    )
