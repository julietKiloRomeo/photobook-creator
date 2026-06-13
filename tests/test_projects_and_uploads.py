"""Tests for the projects + uploads HTTP surface.

Intent-focused: a user creates a project, uploads photos, gets back
what they uploaded, and can fetch thumbnails. Tests use the vacation-20
fixture pack (real JPEGs with EXIF) so the tier-1 pipeline is genuinely
exercised.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _create_project(client: TestClient, name: str = "Test") -> dict:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_project_create_lists_and_get(client: TestClient) -> None:
    created = _create_project(client, name="Italy 2026")
    assert created["name"] == "Italy 2026"

    listed = client.get("/api/projects").json()
    assert any(p["id"] == created["id"] for p in listed)

    fetched = client.get(f"/api/projects/{created['id']}").json()
    assert fetched["id"] == created["id"]


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
