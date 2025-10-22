from analyzer.matching.normalizer import (
    normalize_text,
    duration_bucket,
    normalize_track_title,
)
from analyzer.matching.uid import make_track_uid


def test_normalize_text_removes_diacritics_and_punctuation():
    assert normalize_text("Beyoncé - Halo (Official Video)") == "beyonce halo official video"


def test_duration_bucket_rounds_with_tolerance():
    assert duration_bucket(183, tolerance=2) == "184"
    assert duration_bucket(None) == "na"


def test_make_track_uid_is_deterministic():
    uid1 = make_track_uid("Artist", "Title", "Album", 200)
    uid2 = make_track_uid("Artist", "Title", "Album", 201)
    assert uid1 == uid2
    assert uid1 == make_track_uid("Artist", "Title", "Album", 200)


def test_normalize_track_title_extracts_remix_information():
    normalized = normalize_track_title("From Within (Partyraiser Remix)")
    assert normalized.base == "from within"
    assert normalized.version_tags == ("remix:partyraiser",)


def test_normalize_track_title_ignores_original_and_extended_mix():
    original = normalize_track_title("Noisecontrollers - Unite (Original Edit)")
    extended = normalize_track_title("Noisecontrollers - Unite (Extended Mix)")
    assert original.base == "noisecontrollers unite"
    assert extended.base == "noisecontrollers unite"
    assert original.version_tags == ()
    assert extended.version_tags == ()


def test_track_uid_differs_for_distinct_remix_versions():
    base_uid = make_track_uid("Headhunterz", "From Within", None, 320)
    remix_uid = make_track_uid("Headhunterz", "From Within (Partyraiser Remix)", None, 320)
    extended_uid = make_track_uid("Noisecontrollers", "Unite (Extended Mix)", None, 305)
    assert base_uid != remix_uid
    assert make_track_uid("Noisecontrollers", "Unite", None, 305) == extended_uid
