from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.models import PhotoFile
from app.services.pipeline import process_file_inline
from tests.conftest import requires_exiftool, run_jobs, write_capture

pytestmark = requires_exiftool


def _seed(env, n: int = 3) -> list[str]:
    ids = []
    for i in range(n):
        f = write_capture(env["photos"], f"DSC_{100 + i}", datetime(2026, 9, 30, 10, i, 0), seed=i)
        ids.append(str(process_file_inline(f["jpeg"]).photo_id))
        process_file_inline(f["raw"])
    return ids


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["components"]["database"]["ok"] and body["components"]["redis"]["ok"]
    assert client.get("/health/live").json() == {"status": "ok"}


def test_missing_unsorted_root_is_not_unhealthy(client, env) -> None:
    (env["photos"] / "unsorted").rmdir()
    roots = client.get("/health").json()["components"]["photo_roots"]
    assert roots["ok"] is True
    unsorted = next(r for r in roots["data"]["roots"] if r["name"] == "unsorted")
    assert unsorted["accessible"] is False and unsorted["required"] is False

    (env["photos"] / "raw").rmdir()
    assert client.get("/health").json()["components"]["photo_roots"]["ok"] is False


def test_list_and_detail(client, env) -> None:
    ids = _seed(env)
    r = client.get("/api/v1/photos", params={"page_size": 2})
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["has_more"]
    first = page["items"][0]
    assert first["base_filename"] == "DSC_102"  # newest first
    assert first["camera"] == "Nikon Z6III"
    assert first["has_raw"] and first["has_jpeg"]
    assert first["thumb_url"].startswith(f"/api/v1/photos/{first['id']}/thumbnail")

    d = client.get(f"/api/v1/photos/{ids[1]}").json()
    assert d["lens_model"] == "NIKKOR Z 50mm f/1.4"
    assert d["aperture"] == 1.4 and d["iso"] == 400
    assert {f["file_type"] for f in d["files"]} == {"jpeg", "raw"}
    assert d["files"][0]["nas_path"].startswith("/mnt/mainpool/photos/z6iii/")
    assert d["files"][0]["smb_path"].startswith("\\\\nas\\photos\\z6iii\\")
    assert d["analysis"]["histogram"]["l"] and len(d["analysis"]["histogram"]["l"]) == 256
    assert d["analysis"]["sharpness_score"] is not None
    assert d["critique"]["provider"] == "local"
    assert d["immich_enabled"] is False and d["immich_url"] is None
    assert d["prev_id"] == ids[2] and d["next_id"] == ids[0]


def test_filters_and_sort(client, env) -> None:
    _seed(env)
    jpeg_only = write_capture(env["photos"], "DSC_900", datetime(2026, 9, 29, 8, 0), raw=False)
    process_file_inline(jpeg_only["jpeg"])
    assert client.get("/api/v1/photos", params={"file_kind": "jpeg_only"}).json()["total"] == 1
    assert client.get("/api/v1/photos", params={"file_kind": "pair"}).json()["total"] == 3
    assert client.get("/api/v1/photos", params={"date_from": "2026-09-30"}).json()["total"] == 3
    items = client.get("/api/v1/photos", params={"sort": "oldest"}).json()["items"]
    assert items[0]["base_filename"] == "DSC_900"
    assert client.get("/api/v1/photos", params={"camera": "NIKON Z6_3", "aperture_max": 2}).json()["total"] == 4
    facets = client.get("/api/v1/photos/facets").json()
    assert facets["cameras"] == ["NIKON Z6_3"]


def test_rating_favorite_reject_tags_notes(client, env) -> None:
    pid = _seed(env, 1)[0]
    r = client.patch(f"/api/v1/photos/{pid}", json={"rating": 4, "favorite": True})
    assert r.status_code == 200 and r.json()["rating"] == 4 and r.json()["favorite"]
    r = client.patch(f"/api/v1/photos/{pid}", json={"flag": "reject"})
    assert r.json()["rejected"] and r.json()["rating"] == 4
    r = client.patch(f"/api/v1/photos/{pid}", json={"tags": ["Portrait", "fall"], "notes": "golden hour"})
    assert sorted(t["name"] for t in r.json()["tags"]) == ["fall", "portrait"]
    assert client.patch(f"/api/v1/photos/{pid}", json={"rating": 9}).status_code == 422
    assert client.get("/api/v1/photos", params={"tag": "fall"}).json()["total"] == 1
    assert client.get("/api/v1/photos", params={"hide_rejected": True}).json()["total"] == 0
    assert client.get("/api/v1/search", params={"q": "golden"}).json()["total"] == 1
    assert client.get("/api/v1/search", params={"q": "NIKKOR"}).json()["total"] == 1


def test_downloads_return_exact_originals(client, env, db) -> None:
    pid = _seed(env, 1)[0]
    d = client.get(f"/api/v1/photos/{pid}").json()
    for f in d["files"]:
        r = client.get(f["download_url"])
        assert r.status_code == 200
        with open(f["container_path"], "rb") as fh:
            assert r.content == fh.read()
        assert f["filename"] in r.headers["content-disposition"]


def test_download_refuses_paths_outside_roots(client, env, db) -> None:
    pid = _seed(env, 1)[0]
    pf = db.scalars(select(PhotoFile).where(PhotoFile.file_type == "jpeg")).first()
    pf.absolute_path = "/etc/passwd"  # simulate a tampered/corrupted DB row
    db.commit()
    assert client.get(f"/api/v1/files/{pf.id}/download").status_code == 403
    assert client.get(f"/api/v1/photos/{pid}").status_code == 200


def test_thumbnail_and_preview(client, env) -> None:
    pid = _seed(env, 1)[0]
    t = client.get(f"/api/v1/photos/{pid}/thumbnail", params={"size": 256})
    assert t.status_code == 200 and t.headers["content-type"] == "image/webp"
    assert "immutable" in t.headers["cache-control"]
    p = client.get(f"/api/v1/photos/{pid}/preview")
    assert p.status_code == 200 and p.content[:2] == b"\xff\xd8"


def test_stats_system_events_jobs(client, env) -> None:
    _seed(env, 2)
    s = client.get("/api/v1/stats").json()
    assert s["totals"]["photos"] == 2 and s["totals"]["raw_files"] == 2 and s["totals"]["jpeg_files"] == 2
    assert s["latest_photo_id"] == s["recent"][0]["id"]
    sysinfo = client.get("/api/v1/system").json()
    assert sysinfo["cache"]["files"] > 0
    roots = sysinfo["components"]["photo_roots"]["data"]["roots"]
    assert {r["name"] for r in roots} == {"jpeg", "raw", "video", "unsorted"}
    assert isinstance(client.get("/api/v1/events").json(), list)
    assert client.post("/api/v1/system/rescan").json()["queued"] is True
    assert client.post("/api/v1/system/rescan").json()["queued"] is False  # deduped while queued
    run_jobs()
    jobs = client.get("/api/v1/jobs").json()
    assert jobs["counts"].get("succeeded", 0) >= 1


def test_orphaned_jobs_are_reaped_and_retryable(client, env) -> None:
    from app.models.enums import JobKind
    from app.services.redis_client import get_redis
    from app.workers.queue import enqueue, reap_orphaned_jobs

    assert enqueue(JobKind.VERIFY, dedupe_key="verify")
    assert reap_orphaned_jobs(grace_seconds=0) == 0  # still in RQ: untouched
    get_redis().flushdb()  # simulate Redis losing its data
    assert reap_orphaned_jobs(grace_seconds=0) == 1

    failed = client.get("/api/v1/jobs", params={"status": "failed"}).json()["items"]
    assert len(failed) == 1 and failed[0]["error"].startswith("lost")
    r = client.post(f"/api/v1/jobs/{failed[0]['id']}/retry")
    assert r.status_code == 202 and r.json()["job_id"]
    assert client.post(f"/api/v1/jobs/{failed[0]['id']}/retry").status_code == 409
    assert client.get("/api/v1/jobs", params={"status": "retried"}).json()["total"] == 1
    run_jobs()
    assert client.get("/api/v1/jobs", params={"status": "succeeded"}).json()["total"] == 1


def test_job_popped_by_dead_worker_does_not_block_dedupe(client, env) -> None:
    from app.models.enums import JobKind
    from app.services.redis_client import get_redis
    from app.workers.queue import enqueue

    first = enqueue(JobKind.VERIFY, dedupe_key="verify")
    assert first and enqueue(JobKind.VERIFY, dedupe_key="verify") is None
    get_redis().delete("rq:queue:ingest")  # popped by a worker that then died: hash still "queued"

    second = enqueue(JobKind.VERIFY, dedupe_key="verify")
    assert second and second != first
    run_jobs()
    jobs = {j["id"]: j for j in client.get("/api/v1/jobs").json()["items"]}
    assert jobs[str(first)]["status"] == "failed" and jobs[str(second)]["status"] == "succeeded"


def test_analyze_endpoint_queues_and_runs(client, env) -> None:
    pid = _seed(env, 1)[0]
    r = client.post(f"/api/v1/photos/{pid}/analyze", json={"technical": True, "ai": True})
    assert r.status_code == 202 and len(r.json()["queued"]) == 2
    run_jobs()
    d = client.get(f"/api/v1/photos/{pid}").json()
    assert d["critique_history"] >= 2


def test_albums(client, env) -> None:
    ids = _seed(env, 2)
    a = client.post("/api/v1/albums", json={"name": "Best of", "photo_ids": ids}).json()
    assert a["photo_count"] == 2 and a["cover_thumb_url"]
    assert client.get("/api/v1/albums").json()[0]["name"] == "Best of"
    assert client.get("/api/v1/photos", params={"album_id": a["id"]}).json()["total"] == 2


def test_metrics(client, env) -> None:
    _seed(env, 1)
    text = client.get("/metrics").text
    for name in (
        "z6iii_photos_total 1.0",
        "z6iii_raw_files_total 1.0",
        "z6iii_jpeg_files_total 1.0",
        "z6iii_ingest_jobs_total",
        "z6iii_analysis_seconds_bucket",
        "z6iii_thumbnail_generation_seconds_count",
        "z6iii_last_ingest_timestamp",
        'z6iii_queue_depth{queue="ingest"}',
    ):
        assert name in text, name


def test_api_token(client, env, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("API_TOKEN", "s3cret")
    get_settings.cache_clear()
    assert client.get("/api/v1/stats").status_code == 401
    assert client.get("/api/v1/stats", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/health/live").status_code == 200
