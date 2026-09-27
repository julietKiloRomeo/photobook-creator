"""Upload-batch provenance.

A ``sources`` row answers one question: which upload batch did this
photo arrive in. The chunked uploader splits a batch across several
requests, so the invariant that matters is that one batch stays one
source however many requests carried it — that is what makes "retry the
rest of this batch" and "undo this import" answerable later.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from shoebox.config import Settings
from shoebox.store import connection, dao


def _create_project(client: TestClient, name: str = "Sources") -> dict:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _create_source(client: TestClient, project_id: str, expected: int) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/sources",
        json={"expected_file_count": expected},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload(
    client: TestClient,
    project_id: str,
    photos: list[Path],
    query: str,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/uploads{query}",
        files=[("files", (p.name, p.read_bytes(), "image/jpeg")) for p in photos],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_creating_a_batch_records_what_it_expects(client: TestClient) -> None:
    project = _create_project(client)

    source = _create_source(client, project["id"], 25)

    assert source["project_id"] == project["id"]
    assert source["kind"] == "upload"
    assert source["expected_file_count"] == 25
    assert source["reference_count"] == 0


def test_creating_a_batch_for_an_unknown_project_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/projects/does-not-exist/sources",
        json={"expected_file_count": 3},
    )
    assert response.status_code == 404


def test_a_chunked_batch_produces_exactly_one_source(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    """The point of the table: three requests, one batch."""
    project = _create_project(client)
    photos = sorted(fixture_pack_dir.glob("vacation_*.jpg"))[:9]
    source = _create_source(client, project["id"], len(photos))
    query = f"?defer_processing=true&source_id={source['id']}"

    for start in range(0, len(photos), 3):
        chunk = _upload(client, project["id"], photos[start : start + 3], query)
        assert chunk["accepted"] == 3

    with connection() as conn:
        sources = dao.list_sources(conn, project["id"])
        references = dao.list_references(conn, project["id"])

    assert [s["id"] for s in sources] == [source["id"]]
    assert len(references) == len(photos)
    assert {r["source_id"] for r in references} == {source["id"]}

    listed = client.get(f"/api/projects/{project['id']}/sources").json()
    assert listed[0]["reference_count"] == len(photos)
    assert listed[0]["expected_file_count"] == len(photos)


def test_an_upload_without_a_source_leaves_provenance_empty(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photos = sorted(fixture_pack_dir.glob("vacation_*.jpg"))[:2]

    body = _upload(client, project["id"], photos, "")

    assert body["accepted"] == 2
    with connection() as conn:
        references = dao.list_references(conn, project["id"])
        assert dao.list_sources(conn, project["id"]) == []
    assert [r["source_id"] for r in references] == [None, None]


def test_a_duplicate_keeps_the_batch_it_first_arrived_in(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photo = [fixture_pack_dir / "vacation_04.jpg"]
    first = _create_source(client, project["id"], 1)
    second = _create_source(client, project["id"], 1)

    assert _upload(client, project["id"], photo, f"?source_id={first['id']}")["accepted"] == 1
    repeat = _upload(client, project["id"], photo, f"?source_id={second['id']}")
    assert repeat["duplicates"] == 1

    with connection() as conn:
        references = dao.list_references(conn, project["id"])
    assert [r["source_id"] for r in references] == [first["id"]]


def test_uploading_into_an_unknown_source_fails_fast(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = _create_project(client)
    photo = fixture_pack_dir / "vacation_05.jpg"

    response = client.post(
        f"/api/projects/{project['id']}/uploads?source_id=src_nope",
        files=[("files", (photo.name, photo.read_bytes(), "image/jpeg"))],
    )

    assert response.status_code == 404
    with connection() as conn:
        assert dao.list_references(conn, project["id"]) == []


def test_uploading_into_another_projects_source_fails_fast(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    mine = _create_project(client, name="Mine")
    theirs = _create_project(client, name="Theirs")
    foreign = _create_source(client, theirs["id"], 1)
    photo = fixture_pack_dir / "vacation_06.jpg"

    response = client.post(
        f"/api/projects/{mine['id']}/uploads?source_id={foreign['id']}",
        files=[("files", (photo.name, photo.read_bytes(), "image/jpeg"))],
    )

    assert response.status_code == 404
    with connection() as conn:
        assert dao.list_references(conn, mine["id"]) == []


def test_batches_are_listed_newest_first(client: TestClient) -> None:
    project = _create_project(client)
    created = [_create_source(client, project["id"], size) for size in (1, 2, 3)]

    listed = client.get(f"/api/projects/{project['id']}/sources").json()

    assert [s["id"] for s in listed] == [s["id"] for s in reversed(created)]


def test_listing_batches_of_an_unknown_project_is_rejected(client: TestClient) -> None:
    assert client.get("/api/projects/does-not-exist/sources").status_code == 404


def test_deleting_a_project_deletes_its_batches(
    client: TestClient, settings: Settings
) -> None:
    project = _create_project(client)
    source = _create_source(client, project["id"], 4)

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204

    with connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert dao.get_source(conn, source["id"]) is None
