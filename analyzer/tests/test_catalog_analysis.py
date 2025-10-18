"""Unit tests for catalog number analysis utilities."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.services.catalog_analysis import (
    CatalogRelease,
    compute_catalog_gaps,
    parse_catalog_number,
)


def test_parse_catalog_number_handles_spacing_and_suffix() -> None:
    """Catalog numbers with whitespace and suffixes are parsed correctly."""

    entry = parse_catalog_number(" EFR 047-DJ ")
    assert entry is not None
    assert entry.prefix == "EFR"
    assert entry.number == 47
    assert entry.suffix == "-DJ"
    assert entry.width == 3


def test_compute_catalog_gaps_detects_missing_number() -> None:
    """A sequential catalog run surfaces a missing identifier."""

    observed_values = [
        "EFR041",
        "EFR042",
        "EFR043",
        "EFR044",
        "EFR045",
        "EFR046",
        "EFR048",
    ]
    observed = [parse_catalog_number(value) for value in observed_values]
    releases = {
        ("EFR", 47): CatalogRelease(
            catalog_id="EFR47",
            release_title="Remedy",
            release_artist="Deathroar",
            release_year=2023,
            release_date=date(2023, 9, 1),
            release_url="https://www.discogs.com/release/30244325-Deathroar-Remedy",
        )
    }
    gaps = compute_catalog_gaps([entry for entry in observed if entry], releases)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.number == 47
    assert gap.catalog_id == "EFR47"
    assert gap.release_title == "Remedy"
    assert gap.sequence_start == "EFR041"
    assert gap.sequence_end == "EFR048"
    assert gap.sequence_expected == 8
    assert gap.sequence_observed == 7
    assert gap.sequence_coverage > 0.85
