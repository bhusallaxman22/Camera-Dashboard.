"""Group frames shot in quick succession into bursts.

Two stills are burst neighbours when they come from the same camera, have the
same pixel dimensions, a focal length within BURST_FOCAL_TOLERANCE, and were
captured no more than BURST_MAX_GAP_SECONDS apart. Bursts are chains: a new
frame joins (and may bridge/merge) the groups of its neighbours.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import BurstGroup, Photo
from app.models.enums import MediaType
from app.utils.timeutil import ensure_aware


def camera_key(photo: Photo) -> str:
    return f"{photo.camera_model or '?'}|{photo.camera_serial or '?'}"


def _compatible(a: Photo, b: Photo, tolerance: float) -> bool:
    if camera_key(a) != camera_key(b):
        return False
    if (a.image_width, a.image_height) != (b.image_width, b.image_height):
        return False
    if a.focal_length and b.focal_length:
        return abs(a.focal_length - b.focal_length) / max(a.focal_length, b.focal_length) <= tolerance
    return True


def _refresh(group: BurstGroup, members: list[Photo]) -> None:
    members = sorted(members, key=lambda p: (ensure_aware(p.capture_time), p.base_filename))
    for i, p in enumerate(members):
        p.burst_group_id = group.id
        p.burst_index = i
    group.photo_count = len(members)
    group.start_time = ensure_aware(members[0].capture_time)
    group.end_time = ensure_aware(members[-1].capture_time)
    if group.cover_photo_id not in {p.id for p in members}:
        group.cover_photo_id = members[0].id


def assign_burst(session: Session, photo: Photo) -> BurstGroup | None:
    """Attach `photo` to a burst if it has neighbours. Idempotent."""
    settings = get_settings()
    if photo.media_type != MediaType.STILL or photo.capture_time is None:
        return None
    t = ensure_aware(photo.capture_time)
    gap = timedelta(seconds=settings.burst_max_gap_seconds)

    neighbours = [
        p
        for p in session.scalars(
            select(Photo).where(
                Photo.id != photo.id,
                Photo.media_type == MediaType.STILL.value,
                Photo.capture_time.between(t - gap, t + gap),
            )
        ).all()
        if _compatible(photo, p, settings.burst_focal_tolerance)
    ]
    if not neighbours:
        return photo.burst_group

    groups: dict = {}
    for n in neighbours:
        if n.burst_group is not None:
            groups[n.burst_group.id] = n.burst_group
    if photo.burst_group is not None:
        groups[photo.burst_group.id] = photo.burst_group

    if groups:
        ordered = sorted(groups.values(), key=lambda g: ensure_aware(g.start_time))
        target = ordered[0]
        members = {p.id: p for g in ordered for p in g.photos}
        for g in ordered[1:]:
            for p in list(g.photos):
                p.burst_group = target
            session.flush()
            session.delete(g)
    else:
        target = BurstGroup(camera_key=camera_key(photo), start_time=t, end_time=t)
        session.add(target)
        session.flush()
        members = {}

    members[photo.id] = photo
    for n in neighbours:
        members[n.id] = n
    for p in members.values():
        p.burst_group = target
    session.flush()
    _refresh(target, list(members.values()))
    return target
