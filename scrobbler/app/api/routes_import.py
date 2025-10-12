from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db.adapter import DatabaseAdapter
from ..schemas.listenbrainz import ListenBrainzImportRequest
from ..core.settings import get_settings
from .deps import get_adapter, verify_api_key
from .job_utils import mark_active_job, request_cancel, resolve_job, resolve_queue, serialize_job

router = APIRouter(prefix="/import", tags=["listenbrainz"], dependencies=[Depends(verify_api_key)])

LISTENBRAINZ_JOB_KEY = "scrobbler:listenbrainz_import_job"


@router.post("/listenbrainz")
async def import_listenbrainz(
    payload: ListenBrainzImportRequest,
    adapter: DatabaseAdapter = Depends(get_adapter),
):
    """Trigger a ListenBrainz import and return summary statistics."""

    config = await adapter.get_config()
    user = payload.user or config.get("listenbrainz_user") or config.get("default_user")
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ListenBrainz user is required")
    token = payload.token or config.get("listenbrainz_token")
    queue = resolve_queue()
    settings = get_settings()
    job = queue.enqueue(
        "scrobbler.app.jobs.listenbrainz.listenbrainz_import_job",
        kwargs={
            "dsn": settings.db_dsn,
            "user": user,
            "token": token,
            "since": payload.since.isoformat() if payload.since else None,
            "page_size": payload.page_size,
            "max_pages": payload.max_pages,
            "base_url": settings.listenbrainz_base_url,
            "musicbrainz_base_url": settings.musicbrainz_base_url,
            "musicbrainz_user_agent": settings.musicbrainz_user_agent,
        },
    )
    job.meta.update({"task": "listenbrainz_import", "status": "queued", "user": user})
    job.save_meta()
    mark_active_job(queue, LISTENBRAINZ_JOB_KEY, job)
    return {"job_id": job.id, "status": job.get_status(), "user": user}


@router.get("/listenbrainz/status")
async def import_listenbrainz_status(job_id: str | None = Query(default=None)):
    """Return the status of the most recent ListenBrainz import job."""

    queue = resolve_queue()
    _, job = resolve_job(queue, LISTENBRAINZ_JOB_KEY, job_id)
    if not job:
        return {"job": None}
    return {"job": serialize_job(job)}


@router.post("/listenbrainz/stop")
async def import_listenbrainz_stop(job_id: str | None = None):
    """Request cancellation of the active ListenBrainz import job."""

    queue = resolve_queue()
    resolved_id, job = resolve_job(queue, LISTENBRAINZ_JOB_KEY, job_id)
    if not job or not resolved_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No running ListenBrainz import job")
    request_cancel(job)
    if job.get_status() in {"queued", "deferred"}:
        job.cancel()
        job.meta["status"] = "cancelled"
        job.save_meta()
    return {"job": serialize_job(job)}
