from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing import cast

from PIL import Image

from photobook.project_store import (
    add_duplicate_photos,
    clear_duplicate_groups,
    create_duplicate_group,
    list_photo_scores_map,
    list_thumbnail_paths,
)


@dataclass(frozen=True)
class DuplicateCandidate:
    photo_path: str
    fingerprint: int
    signature: tuple[int, int, int]


def compute_average_hash(image_path: Path, size: int = 8) -> int:
    with Image.open(image_path) as image:
        image = image.convert("L")
        image = image.resize((size, size), Image.Resampling.BILINEAR)
        if hasattr(image, "get_flattened_data"):
            data = image.get_flattened_data()
        else:
            data = image.getdata()
        pixels = cast(list[int], list(data))  # type: ignore[arg-type]
    average = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | (1 if value >= average else 0)
    return bits


def compute_color_signature(image_path: Path) -> tuple[int, int, int]:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image = image.resize((8, 8), Image.Resampling.BILINEAR)
        if hasattr(image, "get_flattened_data"):
            data = image.get_flattened_data()
        else:
            data = image.getdata()
        pixels = cast(list[tuple[int, int, int]], list(data))  # type: ignore[arg-type]
    red = sum(pixel[0] for pixel in pixels) // len(pixels)
    green = sum(pixel[1] for pixel in pixels) // len(pixels)
    blue = sum(pixel[2] for pixel in pixels) // len(pixels)
    return red, green, blue


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def find_duplicate_groups(db_path: Path, size: int = 256, threshold: int = 6) -> int:
    thumbnail_paths = list_thumbnail_paths(db_path, size)
    score_map = list_photo_scores_map(db_path)
    candidates = [
        DuplicateCandidate(
            photo_path=path,
            fingerprint=compute_average_hash(Path(thumb)),
            signature=compute_color_signature(Path(thumb)),
        )
        for path, thumb in thumbnail_paths.items()
    ]
    candidates.sort(key=lambda candidate: candidate.photo_path)
    clear_duplicate_groups(db_path)
    used: set[str] = set()
    group_count = 0
    for index, candidate in enumerate(candidates):
        if candidate.photo_path in used:
            continue
        group_members = [candidate]
        for other in candidates[index + 1 :]:
            if other.photo_path in used:
                continue
            distance = hamming_distance(candidate.fingerprint, other.fingerprint)
            if distance <= threshold and candidate.signature == other.signature:
                group_members.append(other)
        if len(group_members) <= 1:
            continue
        group_id = create_duplicate_group(db_path)
        best = max(
            group_members,
            key=lambda member: (
                score_map.get(member.photo_path, float("-inf")),
                -hamming_distance(candidate.fingerprint, member.fingerprint),
                member.photo_path,
            ),
        )
        add_duplicate_photos(
            db_path,
            group_id,
            [
                {
                    "photo_path": member.photo_path,
                    "distance": hamming_distance(
                        candidate.fingerprint, member.fingerprint
                    ),
                    "is_best": 1 if member.photo_path == best.photo_path else 0,
                }
                for member in group_members
            ],
        )
        for member in group_members:
            used.add(member.photo_path)
        group_count += 1
    return group_count
