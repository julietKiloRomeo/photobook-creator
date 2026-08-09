"""Tier-2 photo processing pipeline.

Runs on demand (owner taps "Process new photos"). Builds stacks from
references and proposes themes from stacks.

Strategy:

1. **Burst clustering** — references with close ``captured_at`` (within
   ``burst_max_seconds``) form a candidate burst.
2. **Visual confirmation / extension** — within each burst, photos are
   merged if their visual embeddings agree. Across the full set, photos
   that look very similar AND were taken in the same time partition can
   also collapse into a stack (handles "two of the same shot taken from
   slightly different angles minutes apart").
3. **Theme proposal** — stacks are grouped by time partition (gaps of
   ``theme_partition_hours`` hours or more start a new theme). M1 names
   themes ``Day 1``, ``Day 2``, …; renaming is the user's job.

The embedder is pluggable: the default uses the perceptual hash already
computed in tier-1 (cheap, deterministic, perfectly fine for the test
suite and the family-router scenario). A higher-quality embedder
(OpenCLIP ViT-L/14) drops in behind the same interface for production.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import imagehash

# --------------------------------------------------------------- embedding --

class Embedder(Protocol):
    """Returns a similarity score in [0.0, 1.0] for two references.

    Higher = more similar.
    """

    def similarity(self, a: dict, b: dict) -> float: ...


class PhashEmbedder:
    """Default embedder. Uses the pHash already on the reference row.

    Hamming distance over 64 bits ⇒ similarity in [0, 1].
    """

    similarity_threshold: float = 0.88  # ≈ Hamming ≤ 7

    def similarity(self, a: dict, b: dict) -> float:
        pa, pb = a.get("phash"), b.get("phash")
        if not pa or not pb:
            return 0.0
        try:
            ha = imagehash.hex_to_hash(pa)
            hb = imagehash.hex_to_hash(pb)
        except ValueError:
            return 0.0
        distance = ha - hb
        # 64-bit perceptual hash.
        return max(0.0, 1.0 - (distance / 64.0))


# ---------------------------------------------------------------- helpers --

def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _sort_key(ref: dict) -> tuple:
    dt = _parse_iso(ref.get("captured_at"))
    return (dt is None, dt or datetime.max, ref.get("uploaded_at", ""), ref["id"])


# ----------------------------------------------------------------- stacks --

def cluster_stacks(
    references: Sequence[dict],
    *,
    burst_max_seconds: int = 30,
    embedder: Embedder | None = None,
    similarity_threshold: float | None = None,
) -> list[list[str]]:
    """Group references into stacks.

    Returns a list of stacks, each as a list of reference ids.

    Algorithm:
    - Sort by captured_at (None last).
    - Walk: a new stack starts when the time gap from the previous
      reference exceeds ``burst_max_seconds``, OR when both have a
      capture time and visual similarity is below the threshold.
    - References without capture time fall back to "visual-only" stacks
      via embedder similarity against the in-progress stack head.
    """
    if not references:
        return []

    embedder = embedder or PhashEmbedder()
    threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else getattr(embedder, "similarity_threshold", 0.88)
    )

    ordered = sorted(references, key=_sort_key)
    stacks: list[list[dict]] = []

    for ref in ordered:
        if not stacks:
            stacks.append([ref])
            continue
        head = stacks[-1][-1]
        ref_dt = _parse_iso(ref.get("captured_at"))
        head_dt = _parse_iso(head.get("captured_at"))

        same_burst = False
        if ref_dt and head_dt:
            same_burst = abs((ref_dt - head_dt).total_seconds()) <= burst_max_seconds

        visually_similar = embedder.similarity(head, ref) >= threshold

        if same_burst or visually_similar:
            stacks[-1].append(ref)
        else:
            stacks.append([ref])

    return [[r["id"] for r in stack] for stack in stacks]


# ----------------------------------------------------------------- themes --

@dataclass(slots=True)
class ProposedTheme:
    name: str
    stack_ids: list[str]
    #: Earliest capture time in the group, or ``None`` if nothing in it
    #: carries a timestamp. Callers use it for date-based naming.
    started_at: datetime | None = None


def propose_themes(
    stacks: Sequence[dict],
    *,
    theme_partition_hours: int = 6,
    name_for_index: Callable[[int], str] | None = None,
) -> list[ProposedTheme]:
    """Group stacks into themes.

    Stacks are sorted by their earliest reference's capture time, then
    a new theme begins whenever the gap exceeds
    ``theme_partition_hours``. Stacks with no capture time go into the
    last theme (so a project of timestamp-less photos becomes a single
    theme, the simplest sensible default).

    The naming hook lets callers override the default ``Day N``.
    """
    if not stacks:
        return []

    namer = name_for_index or (lambda i: f"Day {i + 1}")

    def _stack_time(stack: dict) -> datetime | None:
        for ref in stack.get("references", []):
            dt = _parse_iso(ref.get("captured_at"))
            if dt is not None:
                return dt
        return None

    sorted_stacks = sorted(stacks, key=lambda s: (_stack_time(s) is None, _stack_time(s) or datetime.max))
    themes: list[list[dict]] = []
    last_time: datetime | None = None
    boundary = timedelta(hours=theme_partition_hours)

    for stack in sorted_stacks:
        st = _stack_time(stack)
        if not themes:
            themes.append([stack])
            last_time = st
            continue
        if st is None or last_time is None or (st - last_time) <= boundary:
            themes[-1].append(stack)
        else:
            themes.append([stack])
        if st is not None:
            last_time = st

    def _group_start(group: list[dict]) -> datetime | None:
        times = [t for t in (_stack_time(s) for s in group) if t is not None]
        return min(times) if times else None

    return [
        ProposedTheme(
            name=namer(i),
            stack_ids=[s["id"] for s in group],
            started_at=_group_start(group),
        )
        for i, group in enumerate(themes)
    ]
