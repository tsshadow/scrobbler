from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any, Callable
from uuid import uuid4
import threading

import httpx
import pytest

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

from scrobbler.app.main import app
from scrobbler.app.services.listenbrainz_service import ListenBrainzImportService


class _InMemoryConnection:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.storage[key] = value

    def get(self, key: str) -> str | None:
        return self.storage.get(key)

    def delete(self, key: str) -> None:
        self.storage.pop(key, None)


class _ImmediateJob:
    def __init__(self, func: Callable[..., Any]) -> None:
        self.id = f"job-{uuid4()}"
        self.func = func
        self.meta: dict[str, Any] = {}
        self.enqueued_at = datetime.utcnow()
        self.started_at: datetime | None = None
        self.ended_at: datetime | None = None
        self._result: Any = None
        self._status = "queued"

    def save_meta(self) -> None:  # pragma: no cover - compatibility shim
        return

    def get_status(self, refresh: bool = False) -> str:
        if self.meta.get("status"):
            return str(self.meta["status"])
        if self.ended_at is not None:
            return "finished"
        if self.started_at is not None:
            return "started"
        return self._status

    def refresh(self) -> None:  # pragma: no cover - compatibility shim
        return

    def cancel(self) -> None:
        self.meta["status"] = "cancelled"
        self.ended_at = datetime.utcnow()
        self._status = "cancelled"

    @property
    def is_finished(self) -> bool:
        return self.ended_at is not None

    @property
    def result(self) -> Any:
        return self._result


class _ImmediateQueue:
    def __init__(self) -> None:
        self.connection = _InMemoryConnection()
        self.jobs: dict[str, _ImmediateJob] = {}

    def enqueue(self, path: str, kwargs: dict[str, Any]):
        module_path, func_name = path.rsplit(".", 1)
        module = import_module(module_path)
        func = getattr(module, func_name)
        job = _ImmediateJob(func)
        self.jobs[job.id] = job
        original_get_current = getattr(module, "get_current_job", None)
        job.started_at = datetime.utcnow()
        exc: Exception | None = None

        def runner() -> None:
            nonlocal exc
            try:
                if original_get_current is not None:
                    module.get_current_job = lambda: job  # type: ignore[attr-defined]
                job._result = func(**kwargs)
                if isinstance(job._result, dict):
                    job.meta.setdefault("result", job._result)
            except Exception as err:  # pragma: no cover - propagated to the test
                exc = err
            finally:
                if original_get_current is not None:
                    module.get_current_job = original_get_current  # type: ignore[attr-defined]

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if exc is not None:
            raise exc
        job.ended_at = datetime.utcnow()
        if job.meta.get("status") not in ("failed", "cancelled"):
            job.meta["status"] = "finished"
        return job

    def fetch_job(self, job_id: str):
        return self.jobs.get(job_id)


def build_listen(ts: int, title: str, artist: str) -> dict[str, Any]:
    return {
        "listened_at": ts,
        "recording_msid": f"msid-{title}",
        "track_metadata": {
            "track_name": title,
            "artist_name": artist,
            "release_name": f"Album {title}",
            "additional_info": {
                "duration": 180,
                "tracknumber": "1",
                "discnumber": "1",
            },
        },
    }


@pytest.mark.asyncio
async def test_listenbrainz_import_endpoint(client, monkeypatch):
    listens = [
        build_listen(1_700_000_000, "Track A", "Artist A"),
        build_listen(1_699_000_000, "Track B", "Artist B"),
    ]

    from analyzer.jobs import queue as analyzer_queue_module

    analyzer_queue_module.get_queue.cache_clear()
    queue = _ImmediateQueue()
    monkeypatch.setattr(analyzer_queue_module, "get_queue", lambda *args, **kwargs: queue)
    from scrobbler.app.api import job_utils as job_utils_module

    monkeypatch.setattr(job_utils_module, "get_queue", lambda *args, **kwargs: queue)

    repo = AnalyzerRepository(app.state.db_adapter.engine)
    for listen in listens:
        metadata = listen["track_metadata"]
        artist_name = metadata["artist_name"]
        normalized_artist = normalize_text(artist_name)
        artist_id = await repo.upsert_artist(
            display_name=artist_name,
            name_normalized=normalized_artist,
            sort_name=normalized_artist,
            mbid=None,
        )

        album_name = metadata.get("release_name")
        album_id = None
        if album_name:
            album_id = await repo.upsert_album(
                title=album_name,
                title_normalized=normalize_text(album_name),
                artist_id=artist_id,
                year=None,
                mbid=None,
            )

        duration = metadata.get("additional_info", {}).get("duration")
        track_uid = make_track_uid(
            artist=artist_name,
            title=metadata["track_name"],
            album=album_name,
            duration=duration,
        )
        track_id = await repo.upsert_track(
            title=metadata["track_name"],
            title_normalized=normalize_text(metadata["track_name"]),
            album_id=album_id,
            primary_artist_id=artist_id,
            duration=duration,
            mbid=None,
            isrc=None,
            acoustid=None,
            track_uid=track_uid,
        )
        await repo.link_track_artists(track_id, [(artist_id, "primary")])

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/user/importer/listens")
        params = dict(request.url.params)
        if "max_ts" in params:
            return httpx.Response(200, json={"payload": {"listens": []}})
        return httpx.Response(200, json={"payload": {"listens": listens}})

    transport = httpx.MockTransport(handler)

    original_service = app.state.listenbrainz_service
    app.state.listenbrainz_service = ListenBrainzImportService(
        app.state.ingest_service,
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs),
    )
    from scrobbler.app.jobs import listenbrainz as listenbrainz_jobs

    monkeypatch.setattr(
        listenbrainz_jobs,
        "ListenBrainzImportService",
        lambda ingest_service, **kwargs: ListenBrainzImportService(
            ingest_service,
            base_url=kwargs.get("base_url", ""),
            musicbrainz_base_url=kwargs.get("musicbrainz_base_url", ""),
            musicbrainz_user_agent=kwargs.get("musicbrainz_user_agent", ""),
            client_factory=lambda **client_kwargs: httpx.AsyncClient(transport=transport, **client_kwargs),
        ),
    )

    try:
        payload = {"user": "importer", "page_size": 100}
        start = await client.post("/api/v1/import/listenbrainz", json=payload)
        assert start.status_code == 200
        start_data = start.json()
        job_id = start_data["job_id"]
        assert start_data["user"] == "importer"

        job_data = None
        for _ in range(3):
            status_response = await client.get(
                "/api/v1/import/listenbrainz/status", params={"job_id": job_id}
            )
            assert status_response.status_code == 200
            job_data = status_response.json()["job"]
            if job_data and job_data.get("status") != "queued":
                break
        assert job_data is not None
        result = job_data["result"]
        assert result["imported"] == 2
        assert result["processed"] == 2
        assert result["skipped"] == 0

        second = await client.post("/api/v1/import/listenbrainz", json=payload)
        assert second.status_code == 200
        second_job = second.json()["job_id"]
        job_second = None
        for _ in range(3):
            status_second = await client.get(
                "/api/v1/import/listenbrainz/status", params={"job_id": second_job}
            )
            assert status_second.status_code == 200
            job_second = status_second.json()["job"]
            if job_second and job_second.get("status") != "queued":
                break
        assert job_second is not None
        result_second = job_second["result"]
        assert result_second["processed"] == 2
        assert result_second["imported"] <= result["imported"]
    finally:
        app.state.listenbrainz_service = original_service
