import pytest

from analyzer.matching.uid import make_track_uid
from analyzer.services.match_service import MatchService


class StubRepo:
    def __init__(self) -> None:
        self.uid_tracks: dict[str, dict] = {}
        self.candidate_results: list[dict] = []

    async def find_track_by_uid(self, uid: str) -> dict | None:
        return self.uid_tracks.get(uid)

    async def search_tracks_by_metadata(self, *, artist, title, duration, limit):
        return self.candidate_results[:limit]


@pytest.mark.asyncio
async def test_match_with_rules_prefers_deterministic_uid_match():
    repo = StubRepo()
    uid = make_track_uid("Headhunterz", "From Within", None, 320)
    repo.uid_tracks[uid] = {"id": 42}
    matcher = MatchService(repo)

    result = await matcher.match_with_rules(
        artist="Headhunterz",
        title="From Within",
        album=None,
        duration=320,
    )

    assert result.status == "matched"
    assert result.track_id == 42
    assert result.confidence == 100


@pytest.mark.asyncio
async def test_match_with_rules_links_extended_mix_to_original():
    repo = StubRepo()
    repo.candidate_results = [
        {
            "track_id": 10,
            "title": "Unite (Extended Mix)",
            "title_normalized": "unite",
            "artist_id": 1,
            "artist_name": "Noisecontrollers",
            "artist_normalized": "noisecontrollers",
            "duration": 320,
        }
    ]
    matcher = MatchService(repo)

    result = await matcher.match_with_rules(
        artist="Noisecontrollers",
        title="Unite",
        album=None,
        duration=320,
    )

    assert result.status == "matched"
    assert result.track_id == 10
    assert result.confidence and result.confidence >= 85


@pytest.mark.asyncio
async def test_match_with_rules_keeps_remix_as_ambiguous():
    repo = StubRepo()
    repo.candidate_results = [
        {
            "track_id": 11,
            "title": "From Within (Partyraiser Remix)",
            "title_normalized": "from within",
            "artist_id": 2,
            "artist_name": "Headhunterz",
            "artist_normalized": "headhunterz",
            "duration": 320,
        }
    ]
    matcher = MatchService(repo)

    result = await matcher.match_with_rules(
        artist="Headhunterz",
        title="From Within",
        album=None,
        duration=320,
    )

    assert result.status == "ambiguous"
    assert not result.track_id
    assert result.candidates
    assert result.candidates[0].track_id == 11
    assert result.candidates[0].confidence < matcher.auto_match_threshold
