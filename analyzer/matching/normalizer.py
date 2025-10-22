"""String normalisation helpers used by the analyzer."""

from __future__ import annotations

import re
from functools import lru_cache
from dataclasses import dataclass
from typing import Iterable, Tuple

from unidecode import unidecode

__all__ = [
    "normalize_text",
    "normalize_tokens",
    "duration_bucket",
    "NormalizedTrackTitle",
    "normalize_track_title",
]

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\u2018\u2019\u201c\u201d\-\u2014()]+")
_FEAT_RE = re.compile(r"\bfeat(?:\.|uring)?\b", re.IGNORECASE)
_VERSION_PAREN_RE = re.compile(r"\(([^)]{1,80})\)")
_TRAILING_VERSION_RE = re.compile(r"(?:[-\u2013\u2014]\s*)([^-\u2013\u2014]+)$")

_IGNORABLE_VERSION_TITLES = {
    "album version",
    "extended edit",
    "extended mix",
    "extended version",
    "original edit",
    "original mix",
    "original version",
}

_IGNORE_SENTINEL = "__ignore__"


@dataclass(frozen=True)
class NormalizedTrackTitle:
    """Container describing the normalized base title and version tags."""

    base: str
    version_tags: Tuple[str, ...]


def _normalize_basic(value: str | None) -> str:
    if not value:
        return ""
    stripped = value.strip().lower()
    ascii_only = unidecode(stripped)
    without_punct = _PUNCT_RE.sub(" ", ascii_only)
    collapsed = _WHITESPACE_RE.sub(" ", without_punct).strip()
    return _FEAT_RE.sub("feat", collapsed)


def _classify_version_segment(segment: str) -> str | None:
    normalized = _normalize_basic(segment)
    if not normalized:
        return None
    if normalized in _IGNORABLE_VERSION_TITLES:
        return _IGNORE_SENTINEL

    tokens = normalized.split()
    if "remix" in tokens:
        descriptor = normalized.replace("remix", "").strip()
        return f"remix:{descriptor}" if descriptor else "remix"
    if "edit" in tokens:
        descriptor = normalized.replace("edit", "").strip()
        return f"edit:{descriptor}" if descriptor else "edit"
    if "mix" in tokens:
        descriptor = normalized.replace("mix", "").strip()
        return f"mix:{descriptor}" if descriptor else "mix"
    if "version" in tokens:
        descriptor = normalized.replace("version", "").strip()
        return f"version:{descriptor}" if descriptor else "version"
    return None


@lru_cache(maxsize=4096)
def normalize_text(value: str | None) -> str:
    """Return a deterministic normalised string for identifier generation."""

    return _normalize_basic(value)


def normalize_tokens(tokens: Iterable[str | None]) -> str:
    """Normalise and join multiple text tokens."""

    parts = [normalize_text(token) for token in tokens if token]
    return " ".join(part for part in parts if part)


@lru_cache(maxsize=4096)
def normalize_track_title(value: str | None) -> NormalizedTrackTitle:
    """Return a normalised track title with extracted version tags."""

    if not value:
        return NormalizedTrackTitle(base="", version_tags=())

    working = value
    detected: list[str] = []

    for match in _VERSION_PAREN_RE.finditer(value):
        segment = match.group(1)
        classification = _classify_version_segment(segment)
        if classification:
            if classification != _IGNORE_SENTINEL:
                detected.append(classification)
            working = working.replace(match.group(0), " ")

    while True:
        trailing = _TRAILING_VERSION_RE.search(working)
        if not trailing:
            break
        segment = trailing.group(1)
        classification = _classify_version_segment(segment)
        if not classification:
            break
        if classification != _IGNORE_SENTINEL:
            detected.append(classification)
        working = working[: trailing.start()]

    normalized_base = _normalize_basic(working)
    unique_tags = tuple(sorted({tag for tag in detected if tag}))
    return NormalizedTrackTitle(base=normalized_base, version_tags=unique_tags)


def duration_bucket(duration: int | None, tolerance: int = 2) -> str:
    """Return a duration bucket string with a configurable tolerance."""

    if duration is None:
        return "na"
    if tolerance < 1:
        tolerance = 1
    bucket = round(duration / tolerance) * tolerance
    return str(int(bucket))
