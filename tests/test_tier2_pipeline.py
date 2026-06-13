"""Tests for the tier-2 pipeline (stack clustering + theme proposal).

Intent: given a set of references with known timestamps, the pipeline
produces a sensible grouping. Tests cover edge cases (missing
timestamps, single photo, single burst).
"""

from __future__ import annotations

from shoebox.pipeline.tier2 import cluster_stacks, propose_themes


def _ref(id_: str, *, at: str | None = None, phash: str | None = None) -> dict:
    return {"id": id_, "captured_at": at, "phash": phash}


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
