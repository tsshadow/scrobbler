"""Match listens against known tracks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Sequence

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

__all__ = ["MatchResult", "MatchCandidate", "MatchService"]


@dataclass(slots=True)
class MatchCandidate:
    track_id: int
    confidence: int
    matched_artist_normalized: str | None
    album_artist_normalized: str | None


@dataclass(slots=True)
class MatchResult:
    status: str
    track_id: int | None
    confidence: int | None
    candidates: Sequence[MatchCandidate]


class MatchService:
    """Provide deterministic and fuzzy listen matching."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        self.repo = repo

    async def deterministic_match(
        self,
        *,
        artist: str | None,
        title: str | None,
        album: str | None,
        duration: int | None,
    ) -> MatchResult:
        uid = make_track_uid(artist=artist, title=title, album=album, duration=duration)
        track = await self.repo.find_track_by_uid(uid)
        if track:
            return MatchResult(status="matched", track_id=track["id"], confidence=100, candidates=[])
        return MatchResult(status="unmatched", track_id=None, confidence=None, candidates=[])

    async def find_candidates(
        self,
        *,
        artist: str | None,
        title: str | None,
        duration: int | None,
        limit: int = 5,
    ) -> AsyncIterator[MatchCandidate]:
        raw_candidates = await self.repo.search_tracks_by_metadata(
            artist=artist, title=title, duration=duration, limit=limit
        )
        scored_candidates = self._score_candidates(
            listen_artist=artist,
            listen_duration=duration,
            candidates=raw_candidates,
        )
        for candidate in scored_candidates[:limit]:
            yield candidate

    def _score_candidates(
        self,
        *,
        listen_artist: str | None,
        listen_duration: int | None,
        candidates: Sequence[dict[str, Any]],
    ) -> list[MatchCandidate]:
        normalized_artist = normalize_text(listen_artist) if listen_artist else None
        best_by_track: dict[int, MatchCandidate] = {}
        for entry in candidates:
            track_id = int(entry["track_id"])
            duration_secs = entry.get("duration_secs")
            matched_artist_normalized = entry.get("matched_artist_normalized")
            album_artist_normalized = entry.get("album_artist_normalized")

            confidence = 50
            if listen_duration is not None and duration_secs is not None:
                if abs(duration_secs - listen_duration) <= 2:
                    confidence = 80

            if normalized_artist:
                if matched_artist_normalized and normalized_artist == matched_artist_normalized:
                    confidence = max(confidence, 90)
                elif (
                    album_artist_normalized
                    and normalized_artist == album_artist_normalized
                ):
                    confidence = max(confidence, 70)

            candidate = best_by_track.get(track_id)
            if candidate is None or confidence > candidate.confidence:
                best_by_track[track_id] = MatchCandidate(
                    track_id=track_id,
                    confidence=confidence,
                    matched_artist_normalized=matched_artist_normalized,
                    album_artist_normalized=album_artist_normalized,
                )
        return sorted(
            best_by_track.values(), key=lambda candidate: candidate.confidence, reverse=True
        )
