"""Utilities to build deterministic track identifiers."""

from __future__ import annotations

import hashlib

from .normalizer import duration_bucket, normalize_tokens, normalize_track_title

__all__ = ["make_track_uid"]


def make_track_uid(
    artist: str | None,
    title: str | None,
    album: str | None = None,
    duration: int | None = None,
) -> str:
    """Return a deterministic SHA1 hash based on normalised metadata."""

    normalized_title = normalize_track_title(title)
    normalized = "|".join(
        [
            normalize_tokens([artist]),
            normalized_title.base,
            normalize_tokens([album]),
            "~".join(normalized_title.version_tags),
            duration_bucket(duration),
        ]
    )
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
