"""Tests for the tier-2 pipeline (stack clustering + theme proposal).

Intent: given a set of references with known timestamps, the pipeline
produces a sensible grouping. Tests cover edge cases (missing
timestamps, single photo, single burst).
"""

from __future__ import annotations

import pytest
from shoebox.pipeline.tier2 import _haversine_meters, cluster_stacks, propose_themes

# Two spots ~3.3 km apart (0.03° of latitude), i.e. beyond the 2 km default.
HOME = (55.6761, 12.5683)
ACROSS_TOWN = (55.7061, 12.5683)
NEXT_DOOR = (55.6763, 12.5686)


def _ref(
    id_: str,
    *,
    at: str | None = None,
    phash: str | None = None,
    gps: tuple[float, float] | None = None,
) -> dict:
    ref = {"id": id_, "captured_at": at, "phash": phash}
    if gps is not None:
        ref["gps_lat"], ref["gps_lon"] = gps
    return ref


def test_empty_reference_set_yields_no_stacks() -> None:
    assert cluster_stacks([]) == []


def test_single_photo_yields_a_single_stack() -> None:
    refs = [_ref("a", at="2026-04-01T10:00:00")]
    assert cluster_stacks(refs) == [["a"]]


def test_close_in_time_photos_form_one_stack() -> None:
    refs = [
        _ref("a", at="2026-04-01T10:00:00"),
        _ref("b", at="2026-04-01T10:00:05"),
        _ref("c", at="2026-04-01T10:00:10"),
    ]
    stacks = cluster_stacks(refs, burst_max_seconds=30)
    assert stacks == [["a", "b", "c"]]


def test_far_apart_photos_form_separate_stacks() -> None:
    refs = [
        _ref("a", at="2026-04-01T10:00:00"),
        _ref("b", at="2026-04-01T10:05:00"),  # 5 min later
    ]
    stacks = cluster_stacks(refs, burst_max_seconds=30)
    assert stacks == [["a"], ["b"]]


def test_visually_identical_photos_collapse_even_if_minutes_apart() -> None:
    same_phash = "0000000000000000"
    refs = [
        _ref("a", at="2026-04-01T10:00:00", phash=same_phash),
        _ref("b", at="2026-04-01T10:05:00", phash=same_phash),
    ]
    stacks = cluster_stacks(refs, burst_max_seconds=30)
    assert stacks == [["a", "b"]]


def test_themes_partition_by_time_gap() -> None:
    stacks = [
        {"id": "s1", "references": [_ref("a", at="2026-04-01T09:00:00")]},
        {"id": "s2", "references": [_ref("b", at="2026-04-01T10:00:00")]},
        {"id": "s3", "references": [_ref("c", at="2026-04-02T09:00:00")]},  # next day
        {"id": "s4", "references": [_ref("d", at="2026-04-02T20:00:00")]},  # evening
    ]
    themes = propose_themes(stacks, theme_partition_hours=6)
    names = [t.name for t in themes]
    assert names == ["Day 1", "Day 2", "Day 3"]
    assert themes[0].stack_ids == ["s1", "s2"]
    assert themes[1].stack_ids == ["s3"]
    assert themes[2].stack_ids == ["s4"]


def test_themes_handle_missing_timestamps_gracefully() -> None:
    stacks = [
        {"id": "s1", "references": [_ref("a")]},
        {"id": "s2", "references": [_ref("b")]},
    ]
    themes = propose_themes(stacks)
    assert len(themes) == 1
    assert set(themes[0].stack_ids) == {"s1", "s2"}


# -------------------------------------------------------------- gps -------

def test_haversine_matches_known_distances() -> None:
    # One degree of longitude on the equator is a full degree of arc.
    assert _haversine_meters((0.0, 0.0), (0.0, 1.0)) == pytest.approx(111_195, abs=100)
    # Copenhagen to Malmö is roughly 28 km as the crow flies.
    assert _haversine_meters(HOME, (55.6050, 13.0038)) == pytest.approx(28_000, abs=1_000)


def test_time_partition_splits_when_locations_are_far_apart() -> None:
    stacks = [
        {"id": "s1", "references": [_ref("a", at="2026-04-01T09:00:00", gps=HOME)]},
        {
            "id": "s2",
            "references": [_ref("b", at="2026-04-01T10:00:00", gps=ACROSS_TOWN)],
        },
    ]
    themes = propose_themes(stacks, theme_partition_hours=6)
    assert [t.stack_ids for t in themes] == [["s1"], ["s2"]]
    assert [t.name for t in themes] == ["Day 1", "Day 2"]


def test_time_partition_at_one_location_stays_one_theme() -> None:
    stacks = [
        {"id": "s1", "references": [_ref("a", at="2026-04-01T09:00:00", gps=HOME)]},
        {
            "id": "s2",
            "references": [_ref("b", at="2026-04-01T10:00:00", gps=NEXT_DOOR)],
        },
    ]
    themes = propose_themes(stacks, theme_partition_hours=6)
    assert [t.stack_ids for t in themes] == [["s1", "s2"]]


def test_themes_ignore_location_when_a_stack_has_no_gps() -> None:
    stacks = [
        {"id": "s1", "references": [_ref("a", at="2026-04-01T09:00:00", gps=HOME)]},
        {"id": "s2", "references": [_ref("b", at="2026-04-01T10:00:00")]},
        {
            "id": "s3",
            "references": [_ref("c", at="2026-04-01T11:00:00", gps=ACROSS_TOWN)],
        },
    ]
    themes = propose_themes(stacks, theme_partition_hours=6)
    # s2 carries no location, so it cannot split; s3 still splits off s1.
    assert [t.stack_ids for t in themes] == [["s1", "s2"], ["s3"]]


def test_visually_identical_photos_far_apart_stay_separate() -> None:
    same_phash = "0000000000000000"
    refs = [
        _ref("a", at="2026-04-01T10:00:00", phash=same_phash, gps=HOME),
        _ref("b", at="2026-04-01T10:00:05", phash=same_phash, gps=ACROSS_TOWN),
    ]
    stacks = cluster_stacks(refs, burst_max_seconds=30)
    assert stacks == [["a"], ["b"]]


def test_visually_identical_photos_at_one_location_still_collapse() -> None:
    same_phash = "0000000000000000"
    refs = [
        _ref("a", at="2026-04-01T10:00:00", phash=same_phash, gps=HOME),
        _ref("b", at="2026-04-01T10:05:00", phash=same_phash, gps=NEXT_DOOR),
    ]
    stacks = cluster_stacks(refs, burst_max_seconds=30)
    assert stacks == [["a", "b"]]


def test_stacks_ignore_location_when_a_reference_has_no_gps() -> None:
    same_phash = "0000000000000000"
    refs = [
        _ref("a", at="2026-04-01T10:00:00", phash=same_phash, gps=HOME),
        _ref("b", at="2026-04-01T10:05:00", phash=same_phash),
    ]
    stacks = cluster_stacks(refs, burst_max_seconds=30)
    assert stacks == [["a", "b"]]
