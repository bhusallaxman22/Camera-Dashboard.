"""Heuristic critique built from EXIF + technical metrics. Always available."""

from __future__ import annotations

from pathlib import Path

from app.ai.base import AIProvider, AIResult, PhotoContext
from app.utils.format import format_shutter


class LocalBasicProvider(AIProvider):
    name = "local"

    def analyze_photo(self, photo: PhotoContext, preview: Path) -> AIResult:
        t = photo.technical or {}
        faces = t.get("face_count") or 0
        face_list = t.get("faces") or []
        brightness = t.get("brightness")
        sharp = t.get("sharpness_score")
        hi = t.get("highlight_clipping_percent") or 0.0
        lo = t.get("shadow_clipping_percent") or 0.0
        exp_label = t.get("exposure_label")
        focal = photo.focal_length_35mm or photo.focal_length
        shutter = photo.shutter_speed
        iso = photo.iso

        largest_face = max((f["w"] * f["h"] for f in face_list), default=0.0)
        scene, subject = self._scene(faces, largest_face, focal, brightness, iso, photo)

        technical: list[str] = []
        issues: list[str] = []
        suggestions: list[str] = []
        composition: list[str] = []

        if sharp is not None:
            technical.append(f"Sharpness estimated {t.get('sharpness_label', '').lower()} ({sharp:.0f}/100).")
        if t.get("exposure_assessment"):
            technical.append(t["exposure_assessment"])
        if photo.aperture and photo.aperture <= 2.0:
            technical.append(f"Shallow depth of field at f/{photo.aperture:g}.")

        if face_list:
            eyes = [e for f in face_list for e in f.get("eyes", []) if e.get("sharpness") is not None]
            if eyes:
                sharp_eyes = sum(1 for e in eyes if e["sharpness"] >= 45)
                technical.append(f"{sharp_eyes} of {len(eyes)} detected eyes look sharp.")
                if sharp_eyes == 0:
                    issues.append("Eyes appear soft; focus may be on the ears, nose or background.")
                    suggestions.append(
                        "Use subject detection (People) with eye AF, or a smaller AF area on the nearest eye."
                    )
            cx = face_list[0]["x"] + face_list[0]["w"] / 2
            if 0.4 < cx < 0.6:
                composition.append("Subject is centred; a rule-of-thirds placement could add tension.")
            else:
                composition.append("Subject placed off-centre, leaving room in the frame.")

        if focal and shutter and shutter > 1 / max(focal, 1):
            issues.append(
                f"Shutter {format_shutter(shutter)} is slower than 1/{round(focal)} at {round(focal)}mm; "
                "camera shake or subject motion is possible (VR helps only with shake)."
            )
            suggestions.append(f"Try 1/{round(focal * 2)} or faster, raising ISO if needed.")
        if sharp is not None and sharp < 25:
            issues.append("Frame is likely blurry.")

        if exp_label in ("over", "good_hi_clip", "high_contrast") and hi > 1.5:
            step = "-0.7" if hi > 5 else "-0.3"
            suggestions.append(
                f"Highlights clip ({hi:.1f}%). Consider {step} EV or check the highlight-weighted meter."
            )
        if exp_label == "under":
            suggestions.append("Image reads dark; consider +0.3 to +0.7 EV next time.")
        if lo > 5 and exp_label != "low_key":
            issues.append(f"{lo:.1f}% of the frame is crushed to black.")
        if iso and iso >= 6400:
            technical.append(f"High ISO ({iso}); expect visible noise in shadows.")
            if shutter and shutter < 1 / 1000 and not faces:
                suggestions.append("Shutter is very fast; you could slow it to lower ISO if motion allows.")

        desc_bits = [scene.capitalize() if scene else "Photo"]
        settings = ", ".join(
            x
            for x in (
                f"{photo.focal_length:g}mm" if photo.focal_length else None,
                f"f/{photo.aperture:g}" if photo.aperture else None,
                format_shutter(shutter),
                f"ISO {iso}" if iso else None,
            )
            if x
        )
        description = f"{desc_bits[0]} shot" + (f" at {settings}" if settings else "")
        if photo.camera:
            description += f" on the {photo.camera}"
        description += "."

        return AIResult(
            scene=scene,
            subject=subject,
            description=description,
            composition=composition,
            technical=technical,
            issues=issues,
            suggestions=suggestions,
            tags=[x for x in (scene, subject) if x],
            aesthetic_score=None,
            confidence=0.35,
            model_name="heuristic",
            model_version="1",
        )

    @staticmethod
    def _scene(
        faces: int,
        largest_face: float,
        focal: float | None,
        brightness: float | None,
        iso: int | None,
        photo: PhotoContext,
    ) -> tuple[str | None, str | None]:
        if faces >= 3:
            return "group", "people"
        if faces >= 1 and largest_face > 0.015:
            return "portrait", "person"
        if brightness is not None and brightness < 0.2 and (iso or 0) >= 3200:
            return "night", None
        dist = photo.focus_distance or ""
        if dist.endswith(" m"):
            try:
                if float(dist.split()[0]) < 0.5:
                    return "close-up", None
            except ValueError:
                pass
        if focal and focal >= 200:
            return "telephoto", None
        if focal and focal <= 35 and faces == 0:
            return "wide", None
        if faces >= 1:
            return "people", "person"
        return None, None
