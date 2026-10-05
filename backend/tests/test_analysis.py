from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageFilter

from app.image.analysis import (
    analyze_image,
    assess_exposure,
    clipping,
    dominant_colors,
    dynamic_range_ev,
    histograms,
    luminance,
    sharpness_label,
    sharpness_score,
)
from app.utils.samples import synthetic_image


def test_sharp_scores_higher_than_blurred(env) -> None:
    sharp = synthetic_image(1600, 1067, seed=3)
    blurred = sharp.filter(ImageFilter.GaussianBlur(6))
    a, b = analyze_image(sharp), analyze_image(blurred)
    assert a.sharpness_score > b.sharpness_score + 20
    assert b.is_blurry
    assert 0 <= b.blur_score <= 1 and b.blur_score > a.blur_score


def test_shallow_dof_subject_still_sharp(env) -> None:
    """A sharp patch on a blurred frame should score via peak tiles, not global."""
    bg = synthetic_image(1600, 1067, seed=5).filter(ImageFilter.GaussianBlur(8))
    subject = synthetic_image(400, 400, seed=9)
    bg.paste(subject, (600, 330))
    r = analyze_image(bg)
    assert r.sharpness_peak > r.sharpness_global * 2
    assert r.sharpness_score >= 45


def test_clipping_and_histogram() -> None:
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[:10] = 255  # 10% white
    arr[10:30] = 128
    lum = luminance(arr)
    hi, lo = clipping(arr, lum)
    assert hi == pytest.approx(10.0)
    assert lo == pytest.approx(70.0)
    h = histograms(arr, lum)
    assert set(h) == {"r", "g", "b", "l"}
    assert all(len(v) == 256 and sum(v) == 10_000 for v in h.values())
    assert h["r"][255] == 1000


def test_exposure_assessment_labels() -> None:
    assert assess_exposure(0.15, 0.0, 10.0)[0] == "under"
    assert assess_exposure(0.75, 8.0, 0.0)[0] == "over"
    assert assess_exposure(0.45, 3.0, 3.0)[0] == "high_contrast"
    assert assess_exposure(0.45, 0.2, 0.1)[0] == "good"
    assert "likely" in assess_exposure(0.15, 0.0, 10.0)[1].lower()


def test_dominant_colors_two_tone() -> None:
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[:, :48] = (200, 30, 30)
    arr[:, 48:] = (20, 20, 220)
    colors = dominant_colors(arr, k=2)
    assert colors[0]["hex"] == "#c81e1e"
    assert colors[0]["fraction"] == pytest.approx(0.75, abs=0.01)


def test_dynamic_range_flat_vs_full() -> None:
    flat = np.full((50, 50), 128, dtype=np.float32)
    full = np.linspace(0, 255, 2500, dtype=np.float32).reshape(50, 50)
    assert dynamic_range_ev(flat) == 0
    assert dynamic_range_ev(full) > 8


def test_score_mapping_and_labels() -> None:
    assert sharpness_score(0) == 0
    assert sharpness_score(15) == 0
    assert sharpness_score(1500) == 100
    assert 40 < sharpness_score(150) < 60
    assert sharpness_label(90) == "Excellent"
    assert sharpness_label(10) == "Likely blurry"


def test_analyze_full_result_shape(env) -> None:
    r = analyze_image(Image.new("RGB", (800, 600), (120, 130, 140)))
    d = r.as_dict()
    for key in ("histogram", "dominant_colors", "highlight_clipping_percent", "faces", "warnings"):
        assert key in d
    # Face model present -> no faces on a flat frame; absent -> None (graceful).
    assert r.face_count in (0, None)
