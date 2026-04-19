from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from photobook.api import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "project.db"
    monkeypatch.setenv("PHOTOBOOK_DB_PATH", str(db_path))
    return TestClient(create_app())


def _project_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.delenv("PHOTOBOOK_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_health_and_darkroom_shell(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    frontpage = client.get("/")
    assert frontpage.status_code == 200
    assert "projects" in frontpage.text.lower()

    shell = client.get("/darkroom/external")
    assert shell.status_code == 200
    assert "darkroom" in shell.text.lower()


def test_reference_upsert_and_list(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    payload = {
        "items": [
            {
                "source": "/photos/a.jpg",
                "source_type": "path",
                "label": "A",
                "metadata": {"camera": "X100"},
            },
            {
                "source": "https://example.com/b.jpg",
                "source_type": "uri",
                "label": "B",
                "metadata": {"camera": "Phone"},
            },
        ]
    }
    res = client.post("/api/intake/references", json=payload)
    assert res.status_code == 200
    assert len(res.json()["items"]) == 2

    update = {
        "items": [
            {
                "source": "/photos/a.jpg",
                "source_type": "path",
                "label": "A2",
                "metadata": {"camera": "X100", "rating": 5},
            }
        ]
    }
    res_update = client.post("/api/intake/references", json=update)
    assert res_update.status_code == 200
    assert len(res_update.json()["items"]) == 2

    listed = client.get("/api/intake/references")
    assert listed.status_code == 200
    items = listed.json()["items"]
    first = next(item for item in items if item["source"] == "/photos/a.jpg")
    assert first["label"] == "A2"
    assert first["metadata"]["rating"] == 5


def test_chapter_page_item_and_export_flow(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    refs = client.post(
        "/api/intake/references",
        json={
            "items": [
                {
                    "source": "/photos/cover.jpg",
                    "source_type": "path",
                    "label": "Cover",
                    "metadata": {},
                }
            ]
        },
    )
    assert refs.status_code == 200
    reference_id = refs.json()["items"][0]["id"]

    create_chapter = client.post("/api/chapters", json={"name": "Summer", "page_count": 2})
    assert create_chapter.status_code == 201
    chapter_id = create_chapter.json()["id"]

    pages = client.get(f"/api/chapters/{chapter_id}/pages")
    assert pages.status_code == 200
    page_items = pages.json()["items"]
    assert len(page_items) == 2
    page_id = page_items[0]["id"]

    photo_item = client.post(
        f"/api/pages/{page_id}/items",
        json={
            "item_type": "photo",
            "reference_id": reference_id,
            "x": 0.1,
            "y": 0.2,
            "w": 0.4,
            "h": 0.5,
            "z": 1,
        },
    )
    assert photo_item.status_code == 201
    item_id = photo_item.json()["id"]

    text_item = client.post(
        f"/api/pages/{page_id}/items",
        json={
            "item_type": "text",
            "text": "Summer 2026",
            "x": 0.2,
            "y": 0.75,
            "w": 0.5,
            "h": 0.1,
            "z": 2,
        },
    )
    assert text_item.status_code == 201

    patch_item = client.patch(f"/api/pages/items/{item_id}", json={"z": 3})
    assert patch_item.status_code == 200

    export = client.post("/api/export", json={})
    assert export.status_code == 200
    data = export.json()
    assert len(data["references"]) == 1
    assert len(data["chapters"]) == 1
    assert data["chapters"][0]["name"] == "Summer"
    assert len(data["chapters"][0]["pages"]) == 2
    assert len(data["chapters"][0]["pages"][0]["items"]) == 2


def test_project_upload_and_reference_image_route(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    project = client.post("/api/projects", json={"name": "Upload Test"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    image = Image.new("RGB", (32, 24), color=(30, 90, 160))
    buf = BytesIO()
    image.save(buf, format="JPEG")
    payload = buf.getvalue()

    upload = client.post(
        f"/api/projects/{project_id}/uploads",
        files=[
            ("files", ("day1.jpg", payload, "image/jpeg")),
            ("relative_paths", (None, "Vacation 2026/Day 1/day1.jpg")),
        ],
    )
    assert upload.status_code == 200
    upload_info = upload.json()["upload"]
    assert upload_info["stored"] == 1
    assert upload_info["supported_images"] == 1

    uploads = client.get(f"/api/projects/{project_id}/uploads")
    assert uploads.status_code == 200
    metadata = uploads.json()["items"][0]["metadata"]
    assert metadata["relative_path"] == "Vacation_2026/Day_1/day1.jpg"

    stacks = client.get(f"/api/projects/{project_id}/stacks")
    assert stacks.status_code == 200
    first_photo_id = stacks.json()["items"][0]["photos"][0]["id"]

    image_response = client.get(f"/api/projects/{project_id}/references/{first_photo_id}/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/")
    assert len(image_response.content) > 0
