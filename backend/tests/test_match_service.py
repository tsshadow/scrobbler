from __future__ import annotations

import pytest

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid
from analyzer.services.match_service import MatchService
from backend.app.core.startup import init_database
from backend.app.db.sqlite_test import create_sqlite_memory_adapter
from backend.app.models import metadata


@pytest.mark.asyncio
async def test_compilation_track_matches_performer_artist():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)
    repo = AnalyzerRepository(adapter.engine)
    matcher = MatchService(repo)

    try:
        compilation_artist = "Various Artists"
        performer_artist = "Drokz"
        track_title = "Born Hardcore"
        album_title = "Thunderdome"
        duration = 312

        various_id = await repo.upsert_artist(
            display_name=compilation_artist,
            name_normalized=normalize_text(compilation_artist),
            sort_name=normalize_text(compilation_artist),
            mbid=None,
        )
        performer_id = await repo.upsert_artist(
            display_name=performer_artist,
            name_normalized=normalize_text(performer_artist),
            sort_name=normalize_text(performer_artist),
            mbid=None,
        )
        album_id = await repo.upsert_album(
            title=album_title,
            title_normalized=normalize_text(album_title),
            artist_id=various_id,
            year=2004,
            mbid=None,
        )
        track_id = await repo.upsert_track(
            title=track_title,
            title_normalized=normalize_text(track_title),
            album_id=album_id,
            primary_artist_id=various_id,
            duration=duration,
            mbid=None,
            isrc=None,
            acoustid=None,
            track_uid=make_track_uid(
                artist=compilation_artist,
                title=track_title,
                album=album_title,
                duration=duration,
            ),
        )
        await repo.link_track_artists(
            track_id,
            [
                (various_id, "primary"),
                (performer_id, "featured"),
            ],
        )

        candidates = [
            candidate
            async for candidate in matcher.find_candidates(
                artist=performer_artist,
                title=track_title,
                duration=duration,
                limit=5,
            )
        ]

        assert candidates, "Expected at least one candidate for the listen"
        top_candidate = candidates[0]
        assert top_candidate.track_id == track_id
        assert top_candidate.confidence >= 90
        assert top_candidate.matched_artist_normalized == normalize_text(performer_artist)
        assert top_candidate.album_artist_normalized == normalize_text(compilation_artist)
    finally:
        await adapter.close()
