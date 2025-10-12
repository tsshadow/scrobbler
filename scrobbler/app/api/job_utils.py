"""Utility helpers for exposing job status through the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Tuple

from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from ..core.settings import get_settings
from analyzer.jobs.queue import get_queue


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def resolve_queue() -> Queue:
    """Return the shared RQ queue configured for the application."""

    settings = get_settings()
    return get_queue(settings.redis_url, settings.analyzer_queue_name)


def resolve_job(queue: Queue, storage_key: str, job_id: str | None) -> tuple[str | None, Job | None]:
    """Resolve an RQ job either by explicit id or a stored key."""

    resolved = job_id
    if not resolved:
        stored = queue.connection.get(storage_key)
        if isinstance(stored, bytes):
            resolved = stored.decode("utf-8")
        elif isinstance(stored, str):
            resolved = stored
    if not resolved:
        return None, None
    try:
        job = queue.fetch_job(resolved)
    except NoSuchJobError:
        job = None
    if job is None:
        queue.connection.delete(storage_key)
        return resolved, None
    job.refresh()
    return resolved, job


def serialize_job(job: Job) -> dict[str, Any]:
    """Convert a job into a JSON-serialisable payload."""

    job.refresh()
    meta = dict(job.meta or {})
    status = meta.get("status") or job.get_status()
    result = meta.get("result")
    if job.is_finished and job.result is not None:
        result = job.result
        meta.setdefault("result", result)
    payload: dict[str, Any] = {
        "job_id": job.id,
        "state": job.get_status(),
        "status": status,
        "queued_at": _to_iso(job.enqueued_at),
        "started_at": _to_iso(job.started_at),
        "ended_at": _to_iso(job.ended_at),
        "meta": meta,
    }
    if result is not None:
        payload["result"] = result
    return payload


def mark_active_job(queue: Queue, storage_key: str, job: Job) -> None:
    """Store the identifier of the currently relevant job in Redis."""

    queue.connection.set(storage_key, job.id)


def request_cancel(job: Job) -> None:
    """Mark a running job for cancellation."""

    job.refresh()
    job.meta["cancel_requested"] = True
    job.meta["status"] = "cancelling"
    job.save_meta()
