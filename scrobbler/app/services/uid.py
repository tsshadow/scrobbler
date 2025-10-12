"""Utilities for building deterministic track identifiers.

This module mirrors the helper used by the analyzer so the scrobbler can
generate compatible track identifiers without importing analyzer code. The
helper normalises noisy metadata, buckets durations into coarse ranges and
produces a SHA1 hash that uniquely represents a track.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

__all__ = ["make_track_uid", "pick_primary_artist"]

_WHITESPACE_RE = re.compile(r"\s+")
_NOISE_TOKENS = [
    r"\(official\s*video\)",
    r"\(lyrics?\)",
    r"\[lyrics?\]",
    r"\(hd\)",
    r"\[hd\]",
    r"\(audio\)",
    r"\(remastered.*?\)",
    r"\(explicit\)",
    r"-\s*topic",
]
_NOISE_RE = re.compile("|".join(_NOISE_TOKENS), flags=re.IGNORECASE)


def _normalize(text: str) -> str:
    """Lowercase, trim, and collapse noise tokens from the provided text."""

    cleaned = text.strip().lower()
    cleaned = _NOISE_RE.sub("", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned


def _duration_bucket(duration_ms: Optional[int]) -> Optional[int]:
    """Return a 2-second bucket for durations to smooth out jitter."""

    if not duration_ms or duration_ms <= 0:
        return None
    return round(duration_ms / 2000)


def make_track_uid(
    title: str,
    primary_artist: str,
    duration_ms: Optional[int] = None,
) -> str:
    """Return a deterministic SHA1 hash for the supplied metadata.

    The helper mirrors the analyzer's behaviour so both services agree on
    `track_uid` values. Durations are optional; when omitted the hash is based
    on title and artist alone.
    """

    normalized_title = _normalize(title)
    normalized_artist = _normalize(primary_artist)
    bucket = _duration_bucket(duration_ms)
    payload = (
        f"{normalized_title}|{normalized_artist}"
        if bucket is None
        else f"{normalized_title}|{normalized_artist}|{bucket}"
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def pick_primary_artist(artists: Iterable[str]) -> str:
    """Return the first non-empty artist string as the primary credit."""

    for artist in artists:
        if artist and artist.strip():
            return artist
    return ""

