"""Match listens against known tracks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Sequence

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text, normalize_track_title
from analyzer.matching.uid import make_track_uid

from rapidfuzz import fuzz

__all__ = ["MatchResult", "MatchCandidate", "MatchService"]


@dataclass(slots=True)
class MatchCandidate:
    track_id: int
    confidence: int


@dataclass(slots=True)
class MatchResult:
    status: str
    track_id: int | None
    confidence: int | None
    candidates: Sequence[MatchCandidate]


@dataclass(slots=True)
class _ScoredCandidate:
    track_id: int
    confidence: int
    strict: bool


class MatchService:
    """Provide deterministic and fuzzy listen matching."""

    def __init__(
        self,
        repo: AnalyzerRepository,
        *,
        auto_match_threshold: int = 85,
        candidate_limit: int = 5,
    ) -> None:
        self.repo = repo
        self.auto_match_threshold = auto_match_threshold
        self.candidate_limit = candidate_limit

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

    async def match_with_rules(
        self,
        *,
        artist: str | None,
        title: str | None,
        album: str | None,
        duration: int | None,
    ) -> MatchResult:
        deterministic = await self.deterministic_match(
            artist=artist, title=title, album=album, duration=duration
        )
        if deterministic.status == "matched":
            return deterministic

        scored = await self._score_candidates(
            artist=artist, title=title, duration=duration, limit=self.candidate_limit
        )
        if not scored:
            return MatchResult(status="unmatched", track_id=None, confidence=None, candidates=[])

        best = scored[0]
        if best.strict and best.confidence >= self.auto_match_threshold:
            return MatchResult(
                status="matched",
                track_id=best.track_id,
                confidence=best.confidence,
                candidates=[],
            )

        candidates = [MatchCandidate(track_id=item.track_id, confidence=item.confidence) for item in scored]
        return MatchResult(status="ambiguous", track_id=None, confidence=None, candidates=candidates)

    async def find_candidates(
        self,
        *,
        artist: str | None,
        title: str | None,
        duration: int | None,
        limit: int = 5,
    ) -> AsyncIterator[MatchCandidate]:
        scored = await self._score_candidates(
            artist=artist, title=title, duration=duration, limit=limit
        )
        for item in scored:
            yield MatchCandidate(track_id=item.track_id, confidence=item.confidence)

    async def _score_candidates(
        self,
        *,
        artist: str | None,
        title: str | None,
        duration: int | None,
        limit: int,
    ) -> list[_ScoredCandidate]:
        normalized_artist = normalize_text(artist) if artist else ""
        normalized_title = normalize_track_title(title)
        raw_candidates = await self.repo.search_tracks_by_metadata(
            artist=artist, title=title, duration=duration, limit=limit
        )
        scored: list[_ScoredCandidate] = []

        for payload in raw_candidates:
            candidate_title = payload.get("title")
            candidate_artist = payload.get("artist_normalized") or normalize_text(payload.get("artist_name"))
            candidate_duration = payload.get("duration")

            normalized_candidate = normalize_track_title(candidate_title)
            base_match = (
                normalized_title.base
                and normalized_title.base == normalized_candidate.base
            )
            version_match = normalized_title.version_tags == normalized_candidate.version_tags

            title_score = 0
            if normalized_title.base or normalized_candidate.base:
                title_score = fuzz.token_set_ratio(normalized_title.base, normalized_candidate.base)

            confidence = 0
            strict = False

            if normalized_artist and candidate_artist and normalized_artist == candidate_artist:
                if base_match and version_match:
                    confidence = 90
                    strict = True
                elif base_match:
                    confidence = 60
                elif title_score >= 92:
                    confidence = 75
                elif title_score >= 85:
                    confidence = 65
                elif title_score >= 75:
                    confidence = 60
            else:
                if base_match and version_match:
                    confidence = 70
                elif title_score >= 92:
                    confidence = 60

            if base_match and not version_match and confidence < 60:
                confidence = 60 if normalized_artist and candidate_artist and normalized_artist == candidate_artist else 0

            if confidence == 0:
                continue

            if duration is not None and candidate_duration is not None:
                delta = abs(candidate_duration - duration)
                if delta <= 2:
                    confidence = min(confidence + 10, 95)
                elif delta <= 5:
                    confidence = max(confidence - 5, 0)
                elif delta > 10:
                    confidence = max(confidence - 20, 0)

            scored.append(
                _ScoredCandidate(track_id=payload["track_id"], confidence=confidence, strict=strict)
            )

        scored.sort(key=lambda item: item.confidence, reverse=True)
        return scored[:limit]
