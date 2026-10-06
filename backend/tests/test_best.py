from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models import AICritique
from app.services.best import Candidate, best_eye_sharpness, rank, score_candidate
from tests.conftest import requires_exiftool
from tests.test_api import _seed


def _c(**kw) -> Candidate:
    base = dict(
        photo_id=uuid.uuid4(),
        burst_group_id=None,
        sharpness=None,
        sharpness_peak=None,
        faces=None,
        aesthetic=None,
        rating=0,
        flag="none",
        favorite=False,
    )
    return Candidate(**{**base, **kw})


def test_blend_uses_neutral_prior_for_missing_ai_and_weights_eyes_over_frame_sharpness() -> None:
    assert score_candidate(_c(sharpness=60)).score == 0.6 * 50 + 0.4 * 60
    assert score_candidate(_c(aesthetic=8, sharpness=60)).score == 0.6 * 80 + 0.4 * 60
    faces = [{"eyes": [{"sharpness": 20}, {"sharpness": 70}, {"sharpness": None}]}]
    assert best_eye_sharpness(faces) == 70
    assert score_candidate(_c(aesthetic=5, sharpness=50, faces=faces)).score == 0.6 * 50 + 0.1 * 50 + 0.3 * 70
    # A shallow-focus portrait with sharp eyes beats the same frame with soft eyes.
    sharp_eyes = [{"eyes": [{"sharpness": 95}]}]
    soft_eyes = [{"eyes": [{"sharpness": 25}]}]
    assert (
        score_candidate(_c(sharpness=55, faces=sharp_eyes)).score
        > score_candidate(_c(sharpness=90, faces=soft_eyes)).score
    )
    assert score_candidate(_c()).score == 50


def test_ai_rating_moves_frames_past_unscored_ones() -> None:
    unscored = score_candidate(_c(sharpness=100)).score
    assert score_candidate(_c(aesthetic=7, sharpness=85)).score > unscored
    assert score_candidate(_c(aesthetic=3.5, sharpness=100)).score < unscored


def test_saturated_sharpness_ties_break_on_raw_peak() -> None:
    soft, crisp = _c(sharpness=100, sharpness_peak=900), _c(sharpness=100, sharpness_peak=4100)
    assert [r.photo_id for r in rank([soft, crisp], limit=2)] == [crisp.photo_id, soft.photo_id]


def test_culling_nudges_but_stays_in_range() -> None:
    plain = score_candidate(_c(sharpness=50)).score
    assert score_candidate(_c(sharpness=50, flag="pick", favorite=True, rating=5)).score == plain + 8 + 5 + 6
    assert score_candidate(_c(sharpness=50, rating=1)).score == plain - 6
    assert score_candidate(_c(aesthetic=10, sharpness=100, flag="pick", rating=5)).score == 100


def test_rank_keeps_best_frame_per_burst() -> None:
    burst = uuid.uuid4()
    weak, strong = _c(burst_group_id=burst, sharpness=40), _c(burst_group_id=burst, sharpness=90)
    single = _c(sharpness=70)
    ranked = rank([weak, single, strong], limit=10)
    assert [r.photo_id for r in ranked] == [strong.photo_id, single.photo_id]
    assert len(rank([weak, single, strong], limit=1)) == 1


@requires_exiftool
def test_best_endpoint_excludes_rejects_and_prefers_ai_scores(client, env, db) -> None:
    ids = _seed(env, 3)
    for pid, score in zip(ids, (2.0, 9.0, 6.0), strict=True):
        db.add(
            AICritique(
                photo_id=uuid.UUID(pid),
                provider="ollama",
                status="succeeded",
                aesthetic_score=score,
                created_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
        )
    db.commit()

    body = client.get("/api/v1/photos/best", params={"period": "all"}).json()
    assert body["candidates"] == 3 and body["ai_scored"] == 3
    assert body["items"][0]["photo"]["id"] == ids[1]
    assert body["items"][0]["aesthetic_score"] == 9.0

    client.patch(f"/api/v1/photos/{ids[1]}", json={"flag": "reject"})
    body = client.get("/api/v1/photos/best", params={"period": "all", "limit": 1}).json()
    assert body["candidates"] == 2 and len(body["items"]) == 1 and body["items"][0]["photo"]["id"] == ids[2]

    assert client.get("/api/v1/photos/best", params={"period": "decade"}).status_code == 422
