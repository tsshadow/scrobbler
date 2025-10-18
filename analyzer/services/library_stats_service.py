"""Aggregated statistics for the normalized analyzer library."""

from __future__ import annotations

from datetime import date
from typing import Any

from analyzer.db.repo import AnalyzerRepository
from analyzer.services.catalog_analysis import (
    CatalogGap,
    CatalogRelease,
    compute_catalog_gaps,
    parse_catalog_number,
)

__all__ = ["AnalyzerLibraryStatsService"]


class AnalyzerLibraryStatsService:
    """Expose paginated aggregations over the analyzer library tables."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        """Store the repository used to run aggregation queries."""

        self.repo = repo

    async def artists(self, limit: int, offset: int) -> dict:
        """Return artists ranked by the number of songs in the library."""

        items, total = await self.repo.fetch_library_artists(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def albums(self, limit: int, offset: int) -> dict:
        """Return albums ranked by the number of songs in the library."""

        items, total = await self.repo.fetch_library_albums(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def genres(self, limit: int, offset: int) -> dict:
        """Return genres ranked by the number of songs in the library."""

        items, total = await self.repo.fetch_library_genres(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def labels(self, limit: int, offset: int) -> dict:
        """Return labels with catalog number coverage statistics."""

        items, total = await self.repo.fetch_library_labels(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def label_missing_catalog_numbers(
        self, label_id: int, *, limit: int, offset: int
    ) -> dict | None:
        """Return tracks missing catalog numbers for a given label."""

        result = await self.repo.fetch_label_missing_catalog_numbers(
            label_id=label_id, limit=limit, offset=offset
        )
        if result is None:
            return None
        label_name, items, total = result
        observed = await self.repo.fetch_label_catalog_numbers(label_id)
        releases = await self.repo.fetch_label_release_catalogs(label_id)
        catalog_gaps = _analyze_catalog_gaps(observed, releases)
        return {
            "label_id": label_id,
            "label": label_name,
            "items": items,
            "total": total,
            "catalog_gaps": {
                "items": [_serialize_catalog_gap(gap) for gap in catalog_gaps],
                "total": len(catalog_gaps),
            },
        }

    async def tracks(self, limit: int, offset: int) -> dict:
        """Return tracks ordered by artist and title from the library."""

        items, total = await self.repo.fetch_library_tracks(limit=limit, offset=offset)
        return {"items": items, "total": total}


def _analyze_catalog_gaps(observed_rows: list[dict], release_rows: list[dict]) -> list[CatalogGap]:
    """Return detected catalog gaps for a label."""

    observed = []
    for row in observed_rows:
        entry = parse_catalog_number(row.get("catalog_number"))
        if entry is not None:
            observed.append(entry)

    release_map: dict[tuple[str, int], CatalogRelease] = {}
    for row in release_rows:
        release_entry = parse_catalog_number(row.get("catalog_id"))
        if release_entry is None:
            continue
        key = (release_entry.prefix, release_entry.number)
        release = release_map.get(key)
        release_title = row.get("release_title") or row.get("release_group_title")
        release_artist = row.get("artist")
        release_year = row.get("release_year")
        release_date = row.get("release_date")
        if release_year is None and isinstance(release_date, date):
            release_year = release_date.year
        release_url = _build_release_url(row.get("external_scheme"), row.get("external_value"))
        catalog_id = row.get("catalog_id")
        if release is None:
            release_map[key] = CatalogRelease(
                catalog_id=catalog_id,
                release_title=release_title,
                release_artist=release_artist,
                release_year=release_year,
                release_date=release_date if isinstance(release_date, date) else None,
                release_url=release_url,
            )
            continue
        if release.catalog_id is None and catalog_id:
            release.catalog_id = catalog_id
        if release.release_title is None and release_title:
            release.release_title = release_title
        if release.release_artist is None and release_artist:
            release.release_artist = release_artist
        if release.release_year is None and release_year is not None:
            release.release_year = release_year
        if release.release_date is None and isinstance(release_date, date):
            release.release_date = release_date
        if release.release_url is None and release_url:
            release.release_url = release_url

    return compute_catalog_gaps(observed, release_map)


def _build_release_url(scheme: Any, value: Any) -> str | None:
    """Return an external release URL if available."""

    if not scheme or not value:
        return None
    if isinstance(value, str) and value.startswith("http"):
        return value
    scheme_value = str(scheme).lower()
    text_value = str(value)
    if scheme_value.startswith("discogs"):
        if text_value.isdigit():
            return f"https://www.discogs.com/release/{text_value}"
        cleaned = text_value.lstrip("/")
        return f"https://www.discogs.com/{cleaned}"
    return None


def _serialize_catalog_gap(gap: CatalogGap) -> dict[str, Any]:
    """Convert a catalog gap dataclass into a JSON-serializable mapping."""

    release_date = gap.release_date.isoformat() if isinstance(gap.release_date, date) else None
    return {
        "catalog_id": gap.catalog_id,
        "prefix": gap.prefix,
        "number": gap.number,
        "sequence_start": gap.sequence_start,
        "sequence_end": gap.sequence_end,
        "sequence_expected": gap.sequence_expected,
        "sequence_observed": gap.sequence_observed,
        "sequence_coverage": gap.sequence_coverage,
        "release_title": gap.release_title,
        "release_artist": gap.release_artist,
        "release_year": gap.release_year,
        "release_date": release_date,
        "release_url": gap.release_url,
        "release_catalog_id": gap.release_catalog_id,
    }
