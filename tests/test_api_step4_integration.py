from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from photobook.api import create_app


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


def test_api_cluster_and_dedupe_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app()
    client = TestClient(app)

    upload_files = [
        make_upload("20240101T090000_a.jpg", (2000, 1400), (50, 80, 120)),
        make_upload("20240101T091000_b.jpg", (2200, 1300), (55, 85, 125)),
        make_upload("20240101T140000_c.jpg", (2100, 1500), (60, 90, 130)),
        make_upload("20240101T141500_dup.jpg", (1900, 1200), (65, 95, 135)),
        make_upload("20240101T142000_dup.jpg", (1900, 1200), (65, 95, 135)),
    ]

    response = client.post(
        "/api/ingest", files=[("files", file) for file in upload_files]
    )
    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job_id"]
    cluster_job_id = payload["cluster_job_id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "completed"

    cluster_job = wait_for_job(client, cluster_job_id)
    assert cluster_job["status"] == "completed"

    cluster_items = client.get("/api/clusters")
    assert cluster_items.status_code == 200
    clusters = cluster_items.json()["items"]
    assert len(clusters) == 2

    dedupe_response = client.post("/api/dedupe")
    assert dedupe_response.status_code == 200
    dedupe_job_id = dedupe_response.json()["job_id"]
    dedupe_job = wait_for_job(client, dedupe_job_id)
    assert dedupe_job["status"] == "completed"

    duplicate_items = client.get("/api/duplicates")
    assert duplicate_items.status_code == 200
    groups = duplicate_items.json()["items"]
    assert len(groups) == 1
    assert len(groups[0]["photos"]) == 2
