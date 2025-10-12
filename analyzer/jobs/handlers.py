"""Background job entrypoints for the analyzer queue."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from analyzer.db.repo import AnalyzerRepository
from analyzer.ingestion.filesystem import scan_paths
from analyzer.services.enrich_service import EnrichmentService
from analyzer.services.library_service import LibraryService
from analyzer.services.match_service import MatchService
from rq import get_current_job
from scrobbler.app.db.schema import apply_schema_updates

__all__ = [
    "scan_library_job",
    "enrich_listens_job",
    "reindex_library_job",
    "confirm_listen_match_job",
]


def _create_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(dsn, future=True)


async def _build_services(engine: AsyncEngine) -> tuple[
    AnalyzerRepository, LibraryService, MatchService, EnrichmentService
]:
    await apply_schema_updates(engine)
    repo = AnalyzerRepository(engine)
    library = LibraryService(repo)
    matcher = MatchService(repo)
    enricher = EnrichmentService(repo, matcher)
    return repo, library, matcher, enricher


def scan_library_job(*, dsn: str, paths: Iterable[str], force: bool = False) -> dict:
    async def runner() -> dict:
        engine = _create_engine(dsn)
        try:
            _, library, _, _ = await _build_services(engine)
            job = get_current_job()
            if job:
                job.meta.update(
                    {
                        "task": "scan_library",
                        "status": "running",
                        "processed": 0,
                        "current_path": None,
                        "force": force,
                    }
                )
                job.save_meta()

            cancelled = False

            def should_cancel() -> bool:
                nonlocal cancelled
                if not job:
                    return False
                job.refresh()
                if job.meta.get("cancel_requested"):
                    cancelled = True
                    return True
                return False

            def report_progress(path: str, count: int) -> None:
                if not job:
                    return
                job.meta.update(
                    {
                        "status": "running",
                        "current_path": path,
                        "processed": count,
                    }
                )
                job.save_meta()

            try:
                registered = await scan_paths(
                    library,
                    paths,
                    force=force,
                    on_progress=report_progress,
                    should_cancel=should_cancel,
                )
            except Exception as exc:
                if job:
                    job.meta.update({"status": "failed", "error": str(exc)})
                    job.save_meta()
                raise
            result = {"registered": len(registered), "cancelled": cancelled}
            if job:
                job.meta.update(result)
                job.meta["status"] = "cancelled" if cancelled else "finished"
                job.save_meta()
            return result
        finally:
            await engine.dispose()

    return asyncio.run(runner())


def enrich_listens_job(*, dsn: str, since: str | None, limit: int) -> dict:
    async def runner() -> dict:
        engine = _create_engine(dsn)
        try:
            _, _, matcher, enricher = await _build_services(engine)
            since_dt = datetime.fromisoformat(since) if since else None
            result = await enricher.enrich_pending(since=since_dt, limit=limit)
            return result
        finally:
            await engine.dispose()

    return asyncio.run(runner())


def reindex_library_job(*, dsn: str) -> dict:
    async def runner() -> dict:
        engine = _create_engine(dsn)
        try:
            repo, _, _, _ = await _build_services(engine)
            await repo.refresh_track_uids()
            return {"reindexed": True}
        finally:
            await engine.dispose()

    return asyncio.run(runner())


def confirm_listen_match_job(
    *, dsn: str, listen_id: int, track_id: int, learn_aliases: bool
) -> dict:
    async def runner() -> dict:
        engine = _create_engine(dsn)
        try:
            _, _, matcher, enricher = await _build_services(engine)
            await enricher.confirm_match(
                listen_id=listen_id, track_id=track_id, learn_aliases=learn_aliases
            )
            return {"listen_id": listen_id, "track_id": track_id}
        finally:
            await engine.dispose()

    return asyncio.run(runner())
