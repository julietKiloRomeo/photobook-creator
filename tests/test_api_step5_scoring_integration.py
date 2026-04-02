from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from photobook.api import create_app
from photobook.project_store import list_thumbnail_paths, upsert_photo_scores


def make_upload(
    name: str, size: tuple[int, int], color: tuple[int, int, int]
) -> tuple[str, BytesIO, str]:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)
    return name, buffer, "image/jpeg"


def wait_for_job(
    client: TestClient, job_id: str, timeout: float = 5.0
) -> dict[str, object]:
    start = time.time()
    while time.time() - start < timeout:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("Job did not complete in time")


def test_api_score_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_score_thumbnails(db_path: Path, cache_dir: Path) -> int:
        thumbnail_paths = list_thumbnail_paths(db_path, 256)
        records = [
            {
                "photo_path": photo_path,
                "score": float(index + 1),
                "model": "test-model",
                "device": "cuda",
                "computed_at": "2026-03-29T00:00:00Z",
            }
            for index, photo_path in enumerate(sorted(thumbnail_paths.keys()))
        ]
        upsert_photo_scores(db_path, records)
        return len(records)

    monkeypatch.setattr("photobook.api.score_thumbnails", fake_score_thumbnails)

    app = create_app()
    client = TestClient(app)

    upload_files = [
        make_upload("20240101T090000_a.jpg", (2000, 1400), (50, 80, 120)),
        make_upload("20240101T091000_b.jpg", (2200, 1300), (55, 85, 125)),
        make_upload("20240101T140000_c.jpg", (2100, 1500), (60, 90, 130)),
    ]

    response = client.post(
        "/api/ingest", files=[("files", file) for file in upload_files]
    )
    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job_id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "completed"

    score_response = client.post("/api/score")
    assert score_response.status_code == 200
    score_job_id = score_response.json()["job_id"]
    score_job = wait_for_job(client, score_job_id)
    assert score_job["status"] == "completed"

    score_items = client.get("/api/scores")
    assert score_items.status_code == 200
    scores = score_items.json()["items"]
    assert len(scores) == 3
    assert scores[0]["score"] >= scores[-1]["score"]
