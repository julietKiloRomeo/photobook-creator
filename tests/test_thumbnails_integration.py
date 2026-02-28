from __future__ import annotations

from pathlib import Path

from PIL import Image

from photobook.project_store import (
    ensure_schema,
    list_thumbnails,
    upsert_thumbnail_records,
)
from photobook.thumbnails import (
    generate_thumbnails,
    iter_photo_paths,
    to_thumbnail_record,
)


def make_fixture_image(
    path: Path, size: tuple[int, int], color: tuple[int, int, int]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color)
    image.save(path, format="JPEG")


def test_generate_thumbnails(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    make_fixture_image(fixture_dir / "one.jpg", (3000, 2000), (120, 90, 80))
    make_fixture_image(fixture_dir / "two.jpg", (800, 1400), (20, 160, 140))

    photos = iter_photo_paths([fixture_dir])
    cache_dir = tmp_path / "cache"
    results = generate_thumbnails(photos, cache_dir, [256, 1024])
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_thumbnail_records(
        db_path, [to_thumbnail_record(result) for result in results]
    )
    records = list_thumbnails(db_path)

    assert len(results) == 4
    assert len(records) == 4
    for result in results:
        assert result.output_path.exists()
        assert result.width <= result.size
        assert result.height <= result.size
        assert (
            max(result.width, result.height) == result.size
            or min(result.width, result.height) == result.size
        )
