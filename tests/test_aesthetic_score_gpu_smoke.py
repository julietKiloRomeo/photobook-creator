from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from photobook.aesthetic_score import score_thumbnails
from photobook.project_store import (
    ensure_schema,
    list_thumbnail_paths,
    upsert_thumbnail_records,
)
from photobook.thumbnails import (
    build_thumbnail_path,
    generate_thumbnail,
    to_thumbnail_record,
)


@pytest.mark.gpu
def test_aesthetic_score_gpu_smoke(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    cache_dir = tmp_path / "cache" / "models"
    thumbs_dir = tmp_path / "cache" / "thumbnails"

    image = Image.new("RGB", (1200, 800), (80, 120, 160))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)

    source_path = tmp_path / "20240101T120000_smoke.jpg"
    source_path.write_bytes(buffer.getvalue())

    thumb = generate_thumbnail(
        source_path, build_thumbnail_path(thumbs_dir, source_path, 256), 256
    )
    upsert_thumbnail_records(db_path, [to_thumbnail_record(thumb)])

    assert list_thumbnail_paths(db_path, 256)
    scored = score_thumbnails(db_path, cache_dir)
    assert scored == 1
