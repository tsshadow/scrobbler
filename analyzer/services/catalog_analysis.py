"""Utilities for analyzing catalog number sequences for labels."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import re
from typing import Mapping, Sequence

__all__ = [
    "CatalogNumber",
    "CatalogRelease",
    "CatalogGap",
    "parse_catalog_number",
    "compute_catalog_gaps",
]


@dataclass(frozen=True)
class CatalogNumber:
    """Normalized representation of a catalog number."""

    raw: str
    prefix: str
    number: int
    width: int
    suffix: str


@dataclass
class CatalogRelease:
    """Known release metadata for a catalog identifier."""

    catalog_id: str | None
    release_title: str | None = None
    release_artist: str | None = None
    release_year: int | None = None
    release_date: date | None = None
    release_url: str | None = None


@dataclass
class CatalogGap:
    """Detected missing catalog identifier in a sequential run."""

    catalog_id: str
    prefix: str
    number: int
    sequence_start: str
    sequence_end: str
    sequence_expected: int
    sequence_observed: int
    sequence_coverage: float
    release_title: str | None
    release_artist: str | None
    release_year: int | None
    release_date: date | None
    release_url: str | None
    release_catalog_id: str | None


_CLEAN_PATTERN = re.compile(r"[\s_]+")


def _clean_catalog(value: str) -> str:
    """Return a normalized string suitable for parsing catalog numbers."""

    cleaned = _CLEAN_PATTERN.sub("", value.strip())
    return cleaned


def parse_catalog_number(value: str | None) -> CatalogNumber | None:
    """Parse a raw catalog number into structured components.

    The parser is intentionally permissive: it removes whitespace and underscores
    and accepts prefixes comprised of any leading alphabetic characters followed
    by a contiguous run of digits. Any remaining characters are treated as the
    suffix.
    """

    if not value:
        return None
    cleaned = _clean_catalog(value)
    if not cleaned:
        return None
    match = re.match(r"^(?P<prefix>[A-Za-z]+)(?P<number>\d+)(?P<suffix>.*)$", cleaned)
    if not match:
        return None
    prefix = match.group("prefix").upper()
    digits = match.group("number")
    try:
        number = int(digits)
    except ValueError:
        return None
    suffix = match.group("suffix") or ""
    return CatalogNumber(
        raw=value,
        prefix=prefix,
        number=number,
        width=len(digits),
        suffix=suffix,
    )


def compute_catalog_gaps(
    observed: Sequence[CatalogNumber],
    releases: Mapping[tuple[str, int], CatalogRelease],
    *,
    min_sequence_length: int = 5,
    max_gap: int = 5,
    min_coverage: float = 0.6,
) -> list[CatalogGap]:
    """Return missing catalog IDs inferred from observed sequential runs.

    Args:
        observed: Catalog numbers detected in the local library.
        releases: Known releases keyed by ``(prefix, number)`` for lookup.
        min_sequence_length: Minimum number of observed catalog numbers per
            prefix segment required before gaps are considered reliable.
        max_gap: Maximum jump between successive catalog numbers before a new
            segment is started.
        min_coverage: Minimum ratio of observed catalog numbers to the total
            sequence length required for a segment to be considered sequential.

    Returns:
        A list of :class:`CatalogGap` entries sorted by prefix and number.
    """

    groups: dict[str, list[CatalogNumber]] = defaultdict(list)
    for entry in observed:
        groups[entry.prefix].append(entry)

    gaps: list[CatalogGap] = []
    for prefix, entries in groups.items():
        if not entries:
            continue
        numbers = sorted({entry.number for entry in entries})
        if len(numbers) < min_sequence_length:
            continue
        widths = defaultdict(list)
        for entry in entries:
            widths[entry.number].append(entry.width)

        # Segment the sequence when the gap exceeds the configured threshold.
        segments: list[list[int]] = []
        segment: list[int] = [numbers[0]]
        for current, nxt in zip(numbers, numbers[1:]):
            if nxt - current <= max_gap:
                segment.append(nxt)
                continue
            if len(segment) >= min_sequence_length:
                segments.append(segment)
            segment = [nxt]
        if len(segment) >= min_sequence_length:
            segments.append(segment)

        for segment_numbers in segments:
            if len(segment_numbers) < min_sequence_length:
                continue
            segment_set = set(segment_numbers)
            start = segment_numbers[0]
            end = segment_numbers[-1]
            expected_count = end - start + 1
            observed_count = len(segment_numbers)
            coverage = observed_count / expected_count if expected_count else 0.0
            if coverage < min_coverage:
                continue

            # Determine the most representative width for formatting IDs.
            segment_widths = Counter()
            for number in segment_numbers:
                for width in widths.get(number, []):
                    segment_widths[width] += 1
            default_width = segment_widths.most_common(1)[0][0] if segment_widths else len(str(end))

            for candidate in range(start, end + 1):
                if candidate in segment_set:
                    continue
                release = releases.get((prefix, candidate))
                display_id = _format_catalog(prefix, candidate, default_width, release)
                gap = CatalogGap(
                    catalog_id=display_id,
                    prefix=prefix,
                    number=candidate,
                    sequence_start=_format_catalog(prefix, start, default_width),
                    sequence_end=_format_catalog(prefix, end, default_width),
                    sequence_expected=expected_count,
                    sequence_observed=observed_count,
                    sequence_coverage=coverage,
                    release_title=release.release_title if release else None,
                    release_artist=release.release_artist if release else None,
                    release_year=release.release_year if release else None,
                    release_date=release.release_date if release else None,
                    release_url=release.release_url if release else None,
                    release_catalog_id=release.catalog_id if release else None,
                )
                gaps.append(gap)

    return sorted(gaps, key=lambda entry: (entry.prefix, entry.number))


def _format_catalog(
    prefix: str,
    number: int,
    width: int,
    release: CatalogRelease | None = None,
) -> str:
    """Return a display-ready catalog identifier."""

    if release and release.catalog_id:
        return release.catalog_id
    digits = str(number)
    if width > len(digits):
        digits = digits.zfill(width)
    return f"{prefix}{digits}"
