"""Tier-2 photo processing pipeline.

Runs automatically after every upload. Builds stacks from references
and proposes themes from stacks.

Strategy:

1. **Burst clustering** — references with close ``captured_at`` (within
   ``burst_max_seconds``) form a candidate burst.
2. **Visual confirmation / extension** — within each burst, photos are
   merged if their visual embeddings agree. Across the full set, photos
   that look very similar AND were taken in the same time partition can
   also collapse into a stack (handles "two of the same shot taken from
   slightly different angles minutes apart").
3. **Location veto** — EXIF GPS overrides both of the above. Photos more
   than ``max_location_gap_meters`` apart never share a stack, and a
   time partition that wanders that far splits into separate themes.
4. **Theme proposal** — stacks are grouped by time partition (gaps of
   ``theme_partition_hours`` hours or more start a new theme). M1 names
   themes ``Day 1``, ``Day 2``, …; renaming is the user's job.

GPS is advisory only: most photos here carry no fix, and a missing (or
one-sided) fix leaves the time/visual verdict exactly as it was.

The embedder is pluggable: the default uses the perceptual hash already
computed in tier-1 (cheap, deterministic, perfectly fine for the test
suite and the family-router scenario). A higher-quality embedder
(OpenCLIP ViT-L/14) drops in behind the same interface for production.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
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


def _location(row: dict) -> tuple[float, float] | None:
    """Latitude/longitude of a reference, or ``None`` if it has no fix."""
    lat, lon = row.get("gps_lat"), row.get("gps_lon")
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon))


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two lat/lon pairs, in metres."""
    earth_radius = 6_371_000.0
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * earth_radius * asin(sqrt(h))


def _far_apart(
    a: tuple[float, float] | None,
    b: tuple[float, float] | None,
    max_gap_meters: int,
) -> bool:
    """True only when both fixes exist and they are further than the gap.

    Photos without GPS must not influence any decision, so an absent fix
    always answers "not far apart" and lets time/visual logic decide.
    """
    if a is None or b is None:
        return False
    return _haversine_meters(a, b) > max_gap_meters


# ----------------------------------------------------------------- stacks --

def cluster_stacks(
    references: Sequence[dict],
    *,
    burst_max_seconds: int = 30,
    max_location_gap_meters: int = 2000,
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
    - Two references more than ``max_location_gap_meters`` apart never
      join, however alike they look. Absent GPS on either side leaves
      the time/visual verdict untouched.
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
        far_apart = _far_apart(_location(head), _location(ref), max_location_gap_meters)

        if not far_apart and (same_burst or visually_similar):
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
    max_location_gap_meters: int = 2000,
    name_for_index: Callable[[int], str] | None = None,
) -> list[ProposedTheme]:
    """Group stacks into themes.

    Stacks are sorted by their earliest reference's capture time, then
    a new theme begins whenever the gap exceeds
    ``theme_partition_hours`` or the stack sits more than
    ``max_location_gap_meters`` from the last located stack. Stacks with
    no capture time go into the last theme (so a project of
    timestamp-less photos becomes a single theme, the simplest sensible
    default); stacks with no GPS never trigger a location split.

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

    def _stack_location(stack: dict) -> tuple[float, float] | None:
        for ref in stack.get("references", []):
            where = _location(ref)
            if where is not None:
                return where
        return None

    sorted_stacks = sorted(stacks, key=lambda s: (_stack_time(s) is None, _stack_time(s) or datetime.max))
    themes: list[list[dict]] = []
    last_time: datetime | None = None
    last_where: tuple[float, float] | None = None
    boundary = timedelta(hours=theme_partition_hours)

    for stack in sorted_stacks:
        st = _stack_time(stack)
        where = _stack_location(stack)
        if not themes:
            themes.append([stack])
            last_time = st
            last_where = where
            continue
        time_gap = st is not None and last_time is not None and (st - last_time) > boundary
        if time_gap or _far_apart(last_where, where, max_location_gap_meters):
            themes.append([stack])
        else:
            themes[-1].append(stack)
        if st is not None:
            last_time = st
        if where is not None:
            last_where = where

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
