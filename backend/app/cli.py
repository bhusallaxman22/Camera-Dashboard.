"""Admin CLI: `python -m app.cli <command>` (e.g. inside the backend container)."""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

import typer
from sqlalchemy import select

from app.config import get_settings
from app.log import configure_logging

cli = typer.Typer(help="Z6III AI Studio admin commands", no_args_is_help=True, add_completion=False)


def _echo(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


@cli.command("init-dirs")
def init_dirs() -> None:
    """Create data directories (thumbnails/previews/cache)."""
    s = get_settings()
    for d in (s.thumbnail_root, s.preview_root, s.cache_root):
        d.mkdir(parents=True, exist_ok=True)


@cli.command()
def scan(
    inline: bool = typer.Option(False, help="Process synchronously in this process instead of queueing."),
    force: bool = typer.Option(False, help="Re-read metadata even for unchanged files."),
) -> None:
    """Import existing files from JPEG_ROOT, RAW_ROOT, VIDEO_ROOT and UNSORTED_ROOT (idempotent)."""
    configure_logging()
    from app.database import session_scope
    from app.models.enums import JobKind
    from app.services.pipeline import process_file_inline
    from app.services.scanner import mark_missing, plan_scan
    from app.workers.queue import enqueue

    with session_scope() as s:
        plan = plan_scan(s)
        missing = mark_missing(s, plan.missing)
        if force:
            from app.services.scanner import iter_media_files

            plan.to_ingest = [p for r in get_settings().media_roots.values() if r.is_dir() for p in iter_media_files(r)]
    typer.echo(
        f"seen={plan.total_seen} to_ingest={len(plan.to_ingest)} unchanged={plan.unchanged} "
        f"missing={missing} recent_skipped={plan.skipped_recent}"
    )
    if plan.roots_unavailable:
        typer.secho(f"unavailable roots: {plan.roots_unavailable}", fg="yellow")
    counts: dict[str, int] = {}
    for i, path in enumerate(plan.to_ingest, 1):
        if inline:
            try:
                status = process_file_inline(path, source="scan", force=force).status
            except Exception as exc:
                status = "error"
                typer.secho(f"  {path}: {exc}", fg="red")
        else:
            status = (
                "queued"
                if enqueue(
                    JobKind.INGEST_FILE,
                    dedupe_key=str(path),
                    target_path=str(path),
                    payload={"path": str(path), "source": "scan", "force": force},
                )
                else "already_queued"
            )
        counts[status] = counts.get(status, 0) + 1
        if i % 100 == 0:
            typer.echo(f"  {i}/{len(plan.to_ingest)} {counts}")
    _echo(counts)


@cli.command("rebuild-thumbnails")
def rebuild_thumbnails(
    all_: bool = typer.Option(False, "--all", help="Regenerate even if current."),
    inline: bool = typer.Option(False, help="Run synchronously."),
) -> None:
    """Regenerate previews/thumbnails (only stale ones unless --all)."""
    configure_logging()
    from app.database import session_scope
    from app.models import Photo
    from app.models.enums import JobKind
    from app.services.pipeline import render_step
    from app.workers.queue import enqueue

    with session_scope() as s:
        ids = [str(i) for i in s.scalars(select(Photo.id)).all()]
    n = 0
    for pid in ids:
        if inline:
            if render_step(pid, force=all_).status == "rendered":
                n += 1
        elif enqueue(JobKind.RENDER, dedupe_key=pid, photo_id=pid, payload={"photo_id": pid, "force": all_}):
            n += 1
    typer.echo(f"{'rendered' if inline else 'queued'} {n} of {len(ids)} photos")


@cli.command()
def reanalyze(
    ai: bool = typer.Option(False, help="Also run the configured AI provider."),
    missing_only: bool = typer.Option(False, help="Only photos without analysis."),
    inline: bool = typer.Option(False, help="Run synchronously."),
) -> None:
    """Re-run technical analysis (and optionally AI critique)."""
    configure_logging()
    from app.database import session_scope
    from app.models import Photo, TechnicalAnalysis
    from app.models.enums import JobKind
    from app.services.pipeline import analyze_step
    from app.workers.queue import enqueue

    with session_scope() as s:
        stmt = select(Photo.id)
        if missing_only:
            stmt = stmt.outerjoin(TechnicalAnalysis).where(TechnicalAnalysis.id.is_(None))
        ids = [str(i) for i in s.scalars(stmt).all()]
    for pid in ids:
        if inline:
            analyze_step(pid, with_ai=ai)
        else:
            enqueue(JobKind.ANALYZE, dedupe_key=pid, photo_id=pid, payload={"photo_id": pid, "with_ai": ai})
    typer.echo(f"{'analyzed' if inline else 'queued'} {len(ids)} photos")


@cli.command("verify-files")
def verify_files_cmd() -> None:
    """Check every tracked original still exists (marks missing/restored; never deletes)."""
    configure_logging()
    from app.database import session_scope
    from app.services.scanner import verify_files

    with session_scope() as s:
        _echo(verify_files(s))


@cli.command()
def stats() -> None:
    """Print library statistics."""
    from app.database import session_scope
    from app.services.stats import compute_stats

    with session_scope() as s:
        out = compute_stats(s, recent_limit=0).model_dump(exclude={"recent"})
    _echo(out)


@cli.command()
def healthcheck(component: str = typer.Argument(..., help="worker | watcher | api")) -> None:
    """Container healthcheck. Exit 0 when healthy."""
    try:
        if component == "worker":
            from rq import Worker

            from app.services.redis_client import get_redis
            from app.workers.queue import worker_is_alive

            host = socket.gethostname()
            ok = any(w.hostname == host and worker_is_alive(w) for w in Worker.all(connection=get_redis()))
        elif component == "watcher":
            from app.workers.queue import watcher_status

            st = watcher_status()
            ok = bool(st and st["age_seconds"] < 60)
        elif component == "api":
            from app.database import db_healthy

            ok = db_healthy()[0]
        else:
            raise typer.BadParameter(component)
    except Exception as exc:
        typer.echo(f"unhealthy: {exc}", err=True)
        sys.exit(1)
    sys.exit(0 if ok else 1)


@cli.command("generate-samples")
def generate_samples(
    out: Path = typer.Argument(..., help="Destination (NOT the real camera library)."),
    count: int = typer.Option(12),
    no_raw: bool = typer.Option(False, help="JPEG only"),
    live: bool = typer.Option(False, help="Write one capture every few seconds (simulates the camera)."),
) -> None:
    """Write synthetic Nikon-style JPEG(+NEF) captures for demos/dev."""
    from app.utils.samples import generate_library

    s = get_settings()
    if out.resolve() == s.photo_root.resolve() or str(out.resolve()).startswith(str(s.photo_root.resolve())):
        typer.secho("Refusing to write into PHOTO_ROOT.", fg="red")
        raise typer.Exit(2)
    if not live:
        paths = generate_library(out, count=count, with_raw=not no_raw)
        typer.echo(f"wrote {len(paths)} files under {out}")
        return
    from datetime import datetime

    base = int(time.time()) % 9000
    for i in range(count):
        generate_library(out, count=1, with_raw=not no_raw, start=datetime.now(), start_index=base + i)
        typer.echo(f"capture {i + 1}/{count}")
        time.sleep(5)


if __name__ == "__main__":
    cli()
