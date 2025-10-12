"""FastAPI router exposing analyzer functionality."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from analyzer.jobs.queue import get_queue
from scrobbler.app.api.job_utils import (
    mark_active_job,
    request_cancel,
    resolve_job,
    resolve_queue,
    serialize_job,
)
from scrobbler.app.core.settings import get_settings

router = APIRouter(prefix="/analyzer", tags=["analyzer"])

ANALYZER_SCAN_JOB_KEY = "scrobbler:analyzer_scan_job"


class ScanLibraryRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    force: bool = False


class EnrichListensRequest(BaseModel):
    since: datetime | None = None
    limit: int = Field(default=500, gt=0, le=5000)


class ConfirmMatchRequest(BaseModel):
    track_id: int
    learn_aliases: bool = True


def _enqueue(job_name: str, **kwargs) -> dict:
    settings = get_settings()
    queue = get_queue(settings.redis_url, settings.analyzer_queue_name)
    if not kwargs.get("paths") and job_name.endswith("scan_library_job"):
        kwargs["paths"] = settings.analyzer_default_paths
    if job_name.endswith("scan_library_job") and not kwargs.get("paths"):
        raise HTTPException(status_code=400, detail="No library paths configured")
    job = queue.enqueue(f"analyzer.jobs.handlers.{job_name}", kwargs={"dsn": settings.db_dsn, **kwargs})
    job.meta.setdefault("status", "queued")
    job.meta.setdefault("task", job_name)
    job.save_meta()
    if job_name == "scan_library_job":
        mark_active_job(queue, ANALYZER_SCAN_JOB_KEY, job)
    return {"job_id": job.id, "status": job.get_status()}


@router.post("/library/scan")
async def scan_library(payload: ScanLibraryRequest):
    """Queue a filesystem scan job for the analyzer."""

    return _enqueue("scan_library_job", paths=payload.paths, force=payload.force)


@router.get("/library/scan/status")
async def scan_status(job_id: str | None = None):
    """Return the status of the active analyzer scan job."""

    queue = resolve_queue()
    _, job = resolve_job(queue, ANALYZER_SCAN_JOB_KEY, job_id)
    if not job:
        return {"job": None}
    return {"job": serialize_job(job)}


@router.post("/library/scan/stop")
async def scan_stop(job_id: str | None = None):
    """Request cancellation of the analyzer scan job."""

    queue = resolve_queue()
    resolved_id, job = resolve_job(queue, ANALYZER_SCAN_JOB_KEY, job_id)
    if not job or not resolved_id:
        raise HTTPException(status_code=404, detail="No active analyzer scan job")
    request_cancel(job)
    if job.get_status() in {"queued", "deferred"}:
        job.cancel()
        job.meta["status"] = "cancelled"
        job.save_meta()
    return {"job": serialize_job(job)}


@router.post("/enrich/listens")
async def enrich_listens(payload: EnrichListensRequest):
    """Queue a listen enrichment job."""

    since = payload.since.isoformat() if payload.since else None
    return _enqueue("enrich_listens_job", since=since, limit=payload.limit)


@router.post("/reindex")
async def reindex_library():
    """Queue a reindex job to recompute track identifiers."""

    return _enqueue("reindex_library_job")


@router.post("/match/{listen_id}/confirm")
async def confirm_match(listen_id: int, payload: ConfirmMatchRequest):
    """Queue a confirmation job for an ambiguous listen."""

    return _enqueue(
        "confirm_listen_match_job",
        listen_id=listen_id,
        track_id=payload.track_id,
        learn_aliases=payload.learn_aliases,
    )
