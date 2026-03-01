from __future__ import annotations

from pathlib import Path

from PIL import Image

from photobook.clustering import cluster_photos_by_time
from photobook.dedupe import find_duplicate_groups
from photobook.project_store import (
    ensure_schema,
    list_clusters,
    list_duplicate_groups,
    list_thumbnails,
    upsert_thumbnail_records,
)
from photobook.thumbnails import generate_thumbnails, to_thumbnail_record


def make_timestamped_image(
    path: Path, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color)
    image.save(path, format="JPEG")


def test_cluster_and_dedupe_flow(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"
    make_timestamped_image(
        photos_dir / "20240101T090000_event1.jpg", (2000, 1400), (40, 80, 120)
    )
    make_timestamped_image(
        photos_dir / "20240101T091000_event1.jpg", (2200, 1300), (45, 85, 125)
    )
    make_timestamped_image(
        photos_dir / "20240101T140000_event2.jpg", (2100, 1500), (60, 90, 130)
    )
    make_timestamped_image(
        photos_dir / "20240101T141500_event2.jpg", (1900, 1200), (65, 95, 135)
    )
    make_timestamped_image(
        photos_dir / "20240101T142000_event2.jpg", (1900, 1200), (65, 95, 135)
    )

    cache_dir = tmp_path / "cache"
    results = generate_thumbnails(
        list(photos_dir.glob("*.jpg")),
        cache_dir,
        [256, 1024],
    )
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_thumbnail_records(
        db_path, [to_thumbnail_record(result) for result in results]
    )

    cluster_count = cluster_photos_by_time(db_path, window_minutes=60)
    clusters = list_clusters(db_path)

    assert cluster_count == 2
    assert len(clusters) == 2
    assert all(cluster["kind"] == "event" for cluster in clusters)
    assert {len(cluster["photos"]) for cluster in clusters} == {2, 3}

    dedupe_count = find_duplicate_groups(db_path, size=256, threshold=0)
    groups = list_duplicate_groups(db_path)

    assert dedupe_count == 1
    assert len(groups) == 1
    assert len(groups[0]["photos"]) == 2
    assert sum(1 for photo in groups[0]["photos"] if photo["is_best"]) == 1

    thumbnails = list_thumbnails(db_path)
    assert len(thumbnails) == 10
