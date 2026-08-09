"""Tests for the projects + uploads HTTP surface.

Intent-focused: a user creates a project, uploads photos, gets back
what they uploaded, and can fetch thumbnails. Tests use the vacation-20
fixture pack (real JPEGs with EXIF) so the tier-1 pipeline is genuinely
exercised.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pillow_heif import from_pillow
from shoebox.api import uploads as uploads_api
from shoebox.app import create_app
from shoebox.config import Settings
from shoebox.jobs import get_runner
from shoebox.pipeline import tier1
from shoebox.pipeline.tier1 import ImageDecodeError, ingest_file
from shoebox.store import connection, dao


def _create_project(client: TestClient, name: str = "Test") -> dict:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_tier_one_decodes_heic(tmp_path: Path) -> None:
    source = tmp_path / "generated.heic"
    from_pillow(Image.new("RGB", (48, 32), "#845ec2")).save(source, quality=90)

    result = ingest_file(
        source_path=source,
        thumbs_dir=tmp_path / "thumbs",
        medium_dir=tmp_path / "medium",
        thumb_small_width=24,
        thumb_medium_width=40,
    )

    assert (result.width, result.height) == (48, 32)
    assert (tmp_path / "thumbs" / f"{result.file_hash}.jpg").is_file()
    assert (tmp_path / "medium" / f"{result.file_hash}.jpg").is_file()


def test_tier_one_classifies_truncated_heic_as_decode_error(tmp_path: Path) -> None:
    source = tmp_path / "truncated.heic"
    from_pillow(Image.new("RGB", (48, 32), "#845ec2")).save(source, quality=90)
    source.write_bytes(source.read_bytes()[:-20])

    with pytest.raises(ImageDecodeError):
        ingest_file(
            source_path=source,
            thumbs_dir=tmp_path / "thumbs",
            medium_dir=tmp_path / "medium",
            thumb_small_width=24,
            thumb_medium_width=40,
        )


def test_project_create_lists_and_get(client: TestClient) -> None:
    created = _create_project(client, name="Italy 2026")
    assert created["name"] == "Italy 2026"

    listed = client.get("/api/projects").json()
    assert any(p["id"] == created["id"] for p in listed)

    fetched = client.get(f"/api/projects/{created['id']}").json()
    assert fetched["id"] == created["id"]


def test_project_photo_count_tracks_unique_uploads(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    assert project["photo_count"] == 0

    photo = fixture_pack_dir / "vacation_02.jpg"
    payload = photo.read_bytes()
    upload = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", ("first.jpg", payload, "image/jpeg")),
            ("files", ("duplicate.jpg", payload, "image/jpeg")),
        ],
    )
    assert upload.status_code == 201
    assert upload.json()["accepted"] == 1
    assert upload.json()["duplicates"] == 1
    get_runner().wait_idle()

    fetched = client.get(f"/api/projects/{project['id']}").json()
    assert fetched["photo_count"] == 1

    listed = client.get("/api/projects").json()
    listed_project = next(item for item in listed if item["id"] == project["id"])
    assert listed_project["photo_count"] == 1


def test_get_unknown_project_returns_404(client: TestClient) -> None:
    response = client.get("/api/projects/does-not-exist")
    assert response.status_code == 404


def test_uploading_a_real_photo_returns_a_reference(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photo = fixture_pack_dir / "vacation_01.jpg"

    with photo.open("rb") as f:
        response = client.post(
            f"/api/projects/{project['id']}/uploads",
            files=[("files", (photo.name, f, "image/jpeg"))],
        )
    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 1
    assert body["duplicates"] == 0
    assert len(body["references"]) == 1
    ref = body["references"][0]
    assert ref["width"] > 0
    assert ref["height"] > 0


def test_uploading_the_same_photo_twice_is_deduplicated(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photo = fixture_pack_dir / "vacation_02.jpg"
    payload_bytes = photo.read_bytes()

    first = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[("files", (photo.name, payload_bytes, "image/jpeg"))],
    ).json()
    assert first["accepted"] == 1

    second = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[("files", (photo.name, payload_bytes, "image/jpeg"))],
    ).json()
    assert second["accepted"] == 0
    assert second["duplicates"] == 1


def test_unique_photo_batch_enqueues_one_processing_job(
    client: TestClient, fixture_pack_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(client)
    photos = [
        fixture_pack_dir / "vacation_01.jpg",
        fixture_pack_dir / "vacation_02.jpg",
    ]
    enqueue_calls: list[tuple[str, str]] = []

    def fake_enqueue(*, project_id: str, kind: str) -> dict:
        enqueue_calls.append((project_id, kind))
        return {"id": "j_fake"}

    monkeypatch.setattr(get_runner(), "enqueue", fake_enqueue)
    response = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", (photo.name, photo.read_bytes(), "image/jpeg"))
            for photo in photos
        ],
    )

    assert response.status_code == 201
    assert response.json()["job_id"] == "j_fake"
    assert enqueue_calls == [(project["id"], "process")]


def test_duplicate_only_upload_does_not_enqueue_processing(
    client: TestClient, fixture_pack_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(client)
    photo = fixture_pack_dir / "vacation_02.jpg"
    enqueue_calls: list[tuple[str, str]] = []

    def fake_enqueue(*, project_id: str, kind: str) -> dict:
        enqueue_calls.append((project_id, kind))
        return {"id": "j_fake"}

    monkeypatch.setattr(get_runner(), "enqueue", fake_enqueue)
    files = [("files", (photo.name, photo.read_bytes(), "image/jpeg"))]
    first = client.post(f"/api/projects/{project['id']}/uploads", files=files)
    assert first.json()["accepted"] == 1
    enqueue_calls.clear()

    duplicate = client.post(f"/api/projects/{project['id']}/uploads", files=files)

    assert duplicate.status_code == 201
    assert duplicate.json()["accepted"] == 0
    assert duplicate.json()["duplicates"] == 1
    assert duplicate.json()["job_id"] is None
    assert enqueue_calls == []


def test_rejected_only_upload_does_not_enqueue_processing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(client)
    enqueue_calls: list[tuple[str, str]] = []

    def fake_enqueue(*, project_id: str, kind: str) -> dict:
        enqueue_calls.append((project_id, kind))
        return {"id": "j_fake"}

    monkeypatch.setattr(get_runner(), "enqueue", fake_enqueue)
    response = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[("files", ("notes.txt", b"not a photo", "text/plain"))],
    )

    assert response.status_code == 201
    assert response.json()["accepted"] == 0
    assert response.json()["job_id"] is None
    assert enqueue_calls == []


def test_failing_exif_metadata_rejects_one_file_and_processes_later_photo(
    client: TestClient,
    fixture_pack_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(client)
    photos = [
        fixture_pack_dir / "vacation_01.jpg",
        fixture_pack_dir / "vacation_02.jpg",
    ]
    real_exif_datetime = tier1._exif_datetime
    metadata_calls = 0
    enqueue_calls: list[tuple[str, str]] = []

    def failing_first_exif(image: Image.Image) -> str | None:
        nonlocal metadata_calls
        metadata_calls += 1
        if metadata_calls == 1:
            raise OSError("malformed EXIF offset")
        return real_exif_datetime(image)

    def fake_enqueue(*, project_id: str, kind: str) -> dict:
        enqueue_calls.append((project_id, kind))
        return {"id": "j_metadata"}

    monkeypatch.setattr(tier1, "_exif_datetime", failing_first_exif)
    monkeypatch.setattr(get_runner(), "enqueue", fake_enqueue)

    response = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", (photo.name, photo.read_bytes(), "image/jpeg"))
            for photo in photos
        ],
    )

    assert response.status_code == 201
    assert response.json()["accepted"] == 1
    assert response.json()["rejected"] == [
        {"filename": photos[0].name, "reason": "file could not be decoded"}
    ]
    assert response.json()["job_id"] == "j_metadata"
    assert enqueue_calls == [(project["id"], "process")]


def test_concurrent_identical_uploads_atomically_classify_one_duplicate(
    client: TestClient,
    fixture_pack_dir: Path,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(client)
    payload = (fixture_pack_dir / "vacation_02.jpg").read_bytes()
    real_connection = uploads_api.connection
    calls = threading.local()
    race = threading.Barrier(2)

    @contextmanager
    def synchronized_connection():
        call_number = getattr(calls, "count", 0) + 1
        calls.count = call_number
        with real_connection() as conn:
            if call_number == 2:
                race.wait(timeout=10)
            try:
                yield conn
            finally:
                if call_number == 2:
                    race.wait(timeout=10)

    monkeypatch.setattr(uploads_api, "connection", synchronized_connection)

    def upload(test_client: TestClient, filename: str, media_type: str):
        return test_client.post(
            f"/api/projects/{project['id']}/uploads",
            files=[("files", (filename, payload, media_type))],
        )

    with (
        TestClient(create_app()) as first_client,
        TestClient(create_app()) as second_client,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(upload, first_client, "first.jpg", "image/jpeg")
        second = executor.submit(upload, second_client, "second.png", "image/png")
        responses = [first.result(), second.result()]

    assert [response.status_code for response in responses] == [201, 201]
    assert sum(response.json()["accepted"] for response in responses) == 1
    assert sum(response.json()["duplicates"] for response in responses) == 1
    with connection() as conn:
        assert len(dao.list_references(conn, project["id"])) == 1
    assert len(list(settings.project_originals_dir(project["id"]).iterdir())) == 1
    for derivative_dir in (
        settings.project_thumbs_dir(project["id"]),
        settings.project_medium_dir(project["id"]),
    ):
        derivatives = list(derivative_dir.iterdir())
        assert len(derivatives) == 1
        with Image.open(derivatives[0]) as derivative:
            derivative.verify()


def test_artifact_move_failure_rolls_back_reference_and_created_files(
    client: TestClient,
    fixture_pack_dir: Path,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(client)
    photo = fixture_pack_dir / "vacation_03.jpg"
    real_move = uploads_api.shutil.move
    move_calls = 0

    def fail_second_move(source, destination):
        nonlocal move_calls
        move_calls += 1
        if move_calls == 2:
            raise OSError("injected artifact move failure")
        return real_move(source, destination)

    monkeypatch.setattr(uploads_api.shutil, "move", fail_second_move)

    with pytest.raises(OSError, match="injected artifact move failure"):
        client.post(
            f"/api/projects/{project['id']}/uploads",
            files=[("files", (photo.name, photo.read_bytes(), "image/jpeg"))],
        )

    with connection() as conn:
        assert dao.list_references(conn, project["id"]) == []
    project_files = [
        path
        for path in settings.project_dir(project["id"]).rglob("*")
        if path.is_file()
    ]
    assert project_files == []


def test_mixed_upload_preserves_valid_files_and_reports_safe_rejections(
    client: TestClient, fixture_pack_dir: Path, settings: Settings
) -> None:
    project = _create_project(client)
    valid_jpeg = (fixture_pack_dir / "vacation_02.jpg").read_bytes()
    corrupt_payload = b"private decoder detail: invalid marker at offset 7"

    response = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", ("valid.jpg", valid_jpeg, "image/jpeg")),
            ("files", (r"folder\corrupt.jpg", corrupt_payload, "image/jpeg")),
            ("files", ("notes.txt", b"not a photo", "text/plain")),
            ("files", ("empty.png", b"", "image/png")),
            ("files", ("duplicate.png", valid_jpeg, "image/png")),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 1
    assert body["duplicates"] == 1
    assert len(body["references"]) == 1
    assert body["rejected"] == [
        {"filename": "corrupt.jpg", "reason": "file could not be decoded"},
        {"filename": "notes.txt", "reason": "unsupported file type"},
        {"filename": "empty.png", "reason": "file is empty"},
    ]
    assert body["job_id"] is not None
    assert corrupt_payload.decode() not in response.text
    assert "invalid marker" not in response.text
    assert len(list(settings.project_originals_dir(project["id"]).iterdir())) == 1


def test_rejected_only_upload_reports_each_file_without_aborting(
    client: TestClient,
) -> None:
    project = _create_project(client)

    response = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", ("broken.jpeg", b"not really a jpeg", "image/jpeg")),
            ("files", (r"documents\notes.txt", b"hello", "text/plain")),
            ("files", ("empty.gif", b"", "image/gif")),
        ],
    )

    assert response.status_code == 201
    assert response.json() == {
        "accepted": 0,
        "duplicates": 0,
        "references": [],
        "rejected": [
            {"filename": "broken.jpeg", "reason": "file could not be decoded"},
            {"filename": "notes.txt", "reason": "unsupported file type"},
            {"filename": "empty.gif", "reason": "file is empty"},
        ],
        "job_id": None,
    }


def test_uploaded_thumbnails_are_servable(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photo = fixture_pack_dir / "vacation_03.jpg"

    with photo.open("rb") as f:
        upload = client.post(
            f"/api/projects/{project['id']}/uploads",
            files=[("files", (photo.name, f, "image/jpeg"))],
        ).json()
    reference_id = upload["references"][0]["id"]

    for kind in ("thumb", "medium", "original"):
        response = client.get(
            f"/api/projects/{project['id']}/references/{reference_id}/{kind}"
        )
        assert response.status_code == 200, kind
        assert response.headers["content-type"].startswith("image/"), kind
        assert len(response.content) > 0, kind


def test_uploading_a_batch_of_photos_accepts_them_all(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photos = sorted(fixture_pack_dir.glob("vacation_*.jpg"))[:5]

    files = []
    handles = []
    try:
        for p in photos:
            f = p.open("rb")
            handles.append(f)
            files.append(("files", (p.name, f, "image/jpeg")))
        response = client.post(
            f"/api/projects/{project['id']}/uploads",
            files=files,
        )
    finally:
        for f in handles:
            f.close()

    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 5
    assert body["duplicates"] == 0


def test_deleting_a_project_returns_no_content_then_404(client: TestClient) -> None:
    project = _create_project(client, name="Delete Me")
    project_id = project["id"]

    del_response = client.delete(f"/api/projects/{project_id}")
    assert del_response.status_code == 204

    fetch_after = client.get(f"/api/projects/{project_id}")
    assert fetch_after.status_code == 404

    del_again = client.delete(f"/api/projects/{project_id}")
    assert del_again.status_code == 404
