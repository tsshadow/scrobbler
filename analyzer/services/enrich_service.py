"""Process listens and enrich them using deterministic matching."""

from __future__ import annotations

from datetime import datetime
from analyzer.db.repo import AnalyzerRepository
from analyzer.services.match_service import MatchService

__all__ = ["EnrichmentService"]


class EnrichmentService:
    """Enrich pending listens by linking them to known tracks."""

    def __init__(self, repo: AnalyzerRepository, matcher: MatchService) -> None:
        self.repo = repo
        self.matcher = matcher

    async def enrich_pending(self, *, since: datetime | None, limit: int) -> dict[str, int]:
        processed = 0
        matched = 0
        ambiguous = 0
        unmatched = 0
        listens = await self.repo.fetch_pending_listens(since=since, limit=limit)
        for listen in listens:
            processed += 1
            result = await self.matcher.match_with_rules(
                artist=listen["artist_name_raw"],
                title=listen["track_title_raw"],
                album=listen.get("album_title_raw"),
                duration=listen.get("duration_secs"),
            )
            if result.status == "matched" and result.track_id:
                matched += 1
                await self.repo.link_listen(
                    listen_id=listen["id"],
                    track_id=result.track_id,
                    status="matched",
                    confidence=result.confidence or 100,
                )
                continue
            candidate_payload = [
                {"track_id": candidate.track_id, "confidence": candidate.confidence}
                for candidate in result.candidates
            ]
            candidates = await self.repo.store_candidates(
                listen_id=listen["id"],
                candidates=candidate_payload,
            )
            if candidates:
                ambiguous += 1
                best_conf = max(candidate["confidence"] for candidate in candidates)
                await self.repo.mark_listen_status(
                    listen_id=listen["id"],
                    status="ambiguous",
                    confidence=best_conf,
                )
            else:
                unmatched += 1
                await self.repo.mark_listen_status(
                    listen_id=listen["id"],
                    status="unmatched",
                    confidence=None,
                )
        return {
            "processed": processed,
            "matched": matched,
            "ambiguous": ambiguous,
            "unmatched": unmatched,
        }

    async def confirm_match(self, *, listen_id: int, track_id: int, learn_aliases: bool) -> None:
        await self.repo.link_listen(
            listen_id=listen_id,
            track_id=track_id,
            status="matched",
            confidence=100,
        )
        if learn_aliases:
            await self.repo.learn_aliases_from_listen(listen_id, track_id)
