from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.ai.base import AIResult
from app.models import Photo
from app.services.ai_apply import apply_critique_to_photo, rating_from_aesthetic
from app.services.photos import merge_ai_tags, set_tags
from tests.conftest import _clear_caches, age_files, requires_exiftool, write_capture


def _result(**kwargs) -> AIResult:
    base = dict(
        scene="portrait",
        subject="person",
        description="A portrait.",
        composition=["centered"],
        technical=["sharp eyes"],
        issues=["busy background"],
        suggestions=["raise shutter"],
        tags=["indoor", "candid"],
        aesthetic_score=7.0,
        confidence=0.9,
        model_name="test",
    )
    base.update(kwargs)
    return AIResult(**base)


@pytest.mark.parametrize(
    ("score", "stars"),
    [(None, None), (0, 0), (1, 0), (3, 2), (6.5, 3), (7, 4), (10, 5), (11, 5)],
)
def test_rating_from_aesthetic(score, stars):
    assert rating_from_aesthetic(score) == stars


@requires_exiftool
def test_apply_fills_empty_culling_fields(env, db):
    files = write_capture(env["photos"], "DSC_0200", datetime(2026, 6, 1, 10, 0), raw=False)
    age_files(env["photos"])
    from app.services.pipeline import process_file_inline

    process_file_inline(files["jpeg"])
    photo = db.scalars(select(Photo)).one()
    photo.rating = 0
    photo.needs_edit = False
    db.flush()

    applied = apply_critique_to_photo(db, photo, _result())
    db.flush()
    assert applied["rating"] == 4
    assert applied["needs_edit"] is True
    assert set(applied["tags_added"]) >= {"indoor", "candid", "portrait"}
    assert photo.rating == 4 and photo.needs_edit is True
    sources = {pt.tag.name: pt.source for pt in photo.tags}
    assert sources["indoor"] == "ai" and sources["portrait"] == "ai"


@requires_exiftool
def test_apply_does_not_overwrite_user_rating_or_clear_needs_edit(env, db):
    files = write_capture(env["photos"], "DSC_0201", datetime(2026, 6, 1, 11, 0), raw=False)
    age_files(env["photos"])
    from app.services.pipeline import process_file_inline

    process_file_inline(files["jpeg"])
    photo = db.scalars(select(Photo)).one()
    photo.rating = 5
    photo.needs_edit = True
    db.flush()

    applied = apply_critique_to_photo(db, photo, _result(issues=[], aesthetic_score=2.0))
    assert "rating" not in applied
    assert "needs_edit" not in applied
    assert photo.rating == 5 and photo.needs_edit is True


@requires_exiftool
def test_low_confidence_skips_rating_and_needs_edit_but_syncs_tags(env, db):
    files = write_capture(env["photos"], "DSC_0202", datetime(2026, 6, 1, 12, 0), raw=False)
    age_files(env["photos"])
    from app.services.pipeline import process_file_inline

    process_file_inline(files["jpeg"])
    photo = db.scalars(select(Photo)).one()
    photo.rating = 0
    photo.needs_edit = False
    db.flush()

    applied = apply_critique_to_photo(db, photo, _result(confidence=0.2))
    assert "rating" not in applied and "needs_edit" not in applied
    assert "indoor" in applied["tags_added"]
    assert photo.rating == 0 and photo.needs_edit is False


@requires_exiftool
def test_merge_ai_tags_preserves_user_tags_across_recritique(env, db):
    files = write_capture(env["photos"], "DSC_0203", datetime(2026, 6, 1, 13, 0), raw=False)
    age_files(env["photos"])
    from app.services.pipeline import process_file_inline

    process_file_inline(files["jpeg"])
    photo = db.scalars(select(Photo)).one()
    set_tags(db, photo, ["keeper", "family"])
    db.flush()

    merge_ai_tags(db, photo, ["indoor", "portrait"])
    db.flush()
    names = {pt.tag.name: pt.source for pt in photo.tags}
    assert names == {"keeper": "user", "family": "user", "indoor": "ai", "portrait": "ai"}

    # User tag that overlaps an AI name stays user-owned.
    merge_ai_tags(db, photo, ["family", "candid"])
    db.flush()
    names = {pt.tag.name: pt.source for pt in photo.tags}
    assert names["family"] == "user"
    assert names["keeper"] == "user"
    assert names["candid"] == "ai"
    assert "indoor" not in names and "portrait" not in names


@requires_exiftool
def test_ai_auto_apply_false_leaves_culling_alone(env, db, monkeypatch):
    monkeypatch.setenv("AI_AUTO_APPLY", "false")
    monkeypatch.setenv("AI_PROVIDER", "local")
    _clear_caches()
    files = write_capture(env["photos"], "DSC_0204", datetime(2026, 6, 1, 14, 0), raw=False)
    age_files(env["photos"])
    from app.services.pipeline import process_file_inline

    process_file_inline(files["jpeg"])
    photo = db.scalars(select(Photo)).one()
    # Local provider runs during process_file_inline; with auto-apply off, rating stays 0
    # unless the local heuristic somehow set needs_edit — rating must remain untouched by apply.
    assert photo.rating == 0
    assert not any(pt.source == "ai" for pt in photo.tags)


@requires_exiftool
def test_pipeline_auto_applies_after_critique(env, db, monkeypatch):
    from app.ai.base import AIResult
    from app.ai.local import LocalBasicProvider
    from app.models import AICritique
    from app.services.pipeline import process_file_inline

    def fake_analyze(self, photo, preview):
        return AIResult(
            scene="portrait",
            subject="person",
            description="A portrait.",
            composition=["centered"],
            technical=["sharp"],
            issues=["busy background"],
            suggestions=["raise shutter"],
            tags=["indoor", "candid"],
            aesthetic_score=7.0,
            confidence=0.9,
            model_name="fake",
        )

    monkeypatch.setattr(LocalBasicProvider, "analyze_photo", fake_analyze)
    files = write_capture(env["photos"], "DSC_0205", datetime(2026, 6, 1, 15, 0), raw=False)
    age_files(env["photos"])
    process_file_inline(files["jpeg"])
    db.expire_all()
    photo = db.scalars(select(Photo)).one()
    critique = db.scalars(select(AICritique).order_by(AICritique.created_at.desc())).first()
    assert critique is not None and critique.status == "succeeded"
    assert photo.rating == 4 and photo.needs_edit is True
    assert critique.applied == {
        "rating": 4,
        "needs_edit": True,
        "tags_added": ["candid", "indoor", "portrait"],
        "tags_removed": [],
    }
    assert {pt.tag.name for pt in photo.tags if pt.source == "ai"} == {"candid", "indoor", "portrait"}
