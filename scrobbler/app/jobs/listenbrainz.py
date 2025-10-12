"""RQ job handlers dedicated to ListenBrainz imports."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from rq import get_current_job
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from scrobbler.app.db.maria import MariaDBAdapter
from scrobbler.app.db.schema import apply_schema_updates
from scrobbler.app.services.ingest_service import IngestService
from scrobbler.app.services.listenbrainz_service import ListenBrainzImportService

__all__ = ["listenbrainz_import_job"]


async def _build_engine(dsn: str) -> AsyncEngine:
    engine = create_async_engine(dsn, future=True)
    await apply_schema_updates(engine)
    return engine


def listenbrainz_import_job(
    *,
    dsn: str,
    user: str,
    token: str | None,
    since: str | None,
    page_size: int,
    max_pages: int | None,
    base_url: str,
    musicbrainz_base_url: str,
    musicbrainz_user_agent: str,
) -> dict[str, Any]:
    """Run a ListenBrainz import in the background worker."""

    async def runner() -> dict[str, Any]:
        engine = await _build_engine(dsn)
        adapter = MariaDBAdapter(engine)
        ingest_service = IngestService(adapter)
        job = get_current_job()
        if job:
            job.meta.update(
                {
                    "task": "listenbrainz_import",
                    "status": "running",
                    "processed": 0,
                    "imported": 0,
                    "skipped": 0,
                    "pages": 0,
                }
            )
            job.save_meta()

        def should_cancel() -> bool:
            if not job:
                return False
            job.refresh()
            if job.meta.get("cancel_requested"):
                return True
            return False

        def report_progress(snapshot: dict[str, Any]) -> None:
            if not job:
                return
            meta = {
                **snapshot,
                "status": snapshot.get("status", "running"),
            }
            job.meta.update(meta)
            job.save_meta()

        try:
            service = ListenBrainzImportService(
                ingest_service,
                base_url=base_url,
                musicbrainz_base_url=musicbrainz_base_url,
                musicbrainz_user_agent=musicbrainz_user_agent,
            )
            result = await service.import_user(
                user=user,
                token=token,
                since=datetime.fromisoformat(since) if since else None,
                page_size=page_size,
                max_pages=max_pages,
                on_progress=report_progress,
                should_cancel=should_cancel,
            )
        except Exception as exc:
            if job:
                job.meta.update({"status": "failed", "error": str(exc)})
                job.save_meta()
            raise
        finally:
            await adapter.close()
        if job:
            job.meta.update(
                {**result, "status": "cancelled" if result.get("cancelled") else "finished", "result": result}
            )
            job.save_meta()
        return result

    return asyncio.run(runner())
