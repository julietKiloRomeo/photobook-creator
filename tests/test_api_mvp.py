from __future__ import annotations

from io import BytesIO
import errno
from pathlib import Path
import time

from fastapi.testclient import TestClient
from PIL import Image

from photobook.api import create_app
from photobook import projects_index


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "project.db"
    monkeypatch.setenv("PHOTOBOOK_DB_PATH", str(db_path))
    return TestClient(create_app())


def _project_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.delenv("PHOTOBOOK_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def _wait_for_operation(client: TestClient, project_id: str, operation_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        response = client.get(f"/api/projects/{project_id}/operations/{operation_id}")
        assert response.status_code == 200
        payload = response.json()["operation"]
        last = payload
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Operation {operation_id} did not complete in time; last={last}")


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


def test_single_photo_stack_is_auto_resolved(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    ingest = client.post(
        "/api/intake/references",
        json={
            "items": [
                {
                    "source": "/photos/solo.jpg",
                    "source_type": "path",
                    "label": "Solo Shot",
                    "metadata": {},
                }
            ]
        },
    )
    assert ingest.status_code == 200
    reference_id = int(ingest.json()["items"][0]["id"])

    stacks = client.get("/api/stacks")
    assert stacks.status_code == 200
    items = stacks.json()["items"]
    assert len(items) == 1
    assert items[0]["photo_ids"] == [reference_id]
    assert items[0]["pick_reference_id"] == reference_id
    assert items[0]["resolved"] is True


def test_project_upload_and_reference_image_route(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    project = client.post("/api/projects", json={"name": "Upload Test"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    initial_progress = client.get(f"/api/projects/{project_id}/uploads/progress")
    assert initial_progress.status_code == 200
    assert initial_progress.json()["phase"] == "idle"

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
    assert upload.status_code == 202
    operation_id = upload.json()["operation_id"]
    done = _wait_for_operation(client, project_id, operation_id)
    assert done["status"] == "completed"
    assert done["phase"] == "completed"
    assert int(done["percent"]) == 100

    upload_progress = client.get(f"/api/projects/{project_id}/uploads/progress")
    assert upload_progress.status_code == 200
    progress_payload = upload_progress.json()
    assert progress_payload["phase"] == "completed"
    assert progress_payload["percent"] == 100
    assert progress_payload["active"] is False

    uploads = client.get(f"/api/projects/{project_id}/uploads")
    assert uploads.status_code == 200
    metadata = uploads.json()["items"][0]["metadata"]
    assert metadata["relative_path"] == "Vacation_2026/Day_1/day1.jpg"

    stacks = client.get(f"/api/projects/{project_id}/stacks")
    assert stacks.status_code == 200
    stacks_payload = stacks.json()
    assert stacks_payload["cluster_state"]["state"] in {"provisional", "final"}
    first_photo_id = stacks_payload["items"][0]["photos"][0]["id"]

    image_response = client.get(f"/api/projects/{project_id}/references/{first_photo_id}/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/")
    assert len(image_response.content) > 0


def test_stack_split_endpoint(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    project = client.post("/api/projects", json={"name": "Split Test"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    image_a = Image.new("RGB", (40, 30), color=(10, 20, 30))
    image_b = Image.new("RGB", (40, 30), color=(10, 20, 30))
    image_c = Image.new("RGB", (40, 30), color=(200, 120, 40))

    path_a = tmp_path / "a.jpg"
    path_b = tmp_path / "b.jpg"
    path_c = tmp_path / "c.jpg"
    image_a.save(path_a)
    image_b.save(path_b)
    image_c.save(path_c)

    seed = client.post(
        f"/api/projects/{project_id}/intake/references",
        json={
            "items": [
                {"source": str(path_a), "source_type": "path", "label": "A", "metadata": {}},
                {"source": str(path_b), "source_type": "path", "label": "B", "metadata": {}},
                {"source": str(path_c), "source_type": "path", "label": "C", "metadata": {}},
            ]
        },
    )
    assert seed.status_code == 200

    process = client.post(f"/api/projects/{project_id}/process", json={})
    assert process.status_code == 200

    stacks_res = client.get(f"/api/projects/{project_id}/stacks")
    assert stacks_res.status_code == 200
    stacks = stacks_res.json()["items"]
    assert all(not str(item["label"]).lower().endswith(" set") for item in stacks)
    target = next((item for item in stacks if len(item["photo_ids"]) > 1), None)
    assert target is not None

    moved_reference_id = int(target["photo_ids"][0])
    split = client.post(
        f"/api/projects/{project_id}/stacks/{target['id']}/split",
        json={"reference_ids": [moved_reference_id], "label": "Manual split"},
    )
    assert split.status_code == 200
    payload = split.json()
    assert payload["status"] == "ok"
    assert payload["result"]["old_stack_id"] == target["id"]
    assert payload["result"]["moved_reference_ids"] == [moved_reference_id]
    assert payload["result"]["new_stack_id"].startswith("s-")
    new_stack_id = payload["result"]["new_stack_id"]

    process_after_split = client.post(f"/api/projects/{project_id}/process", json={})
    assert process_after_split.status_code == 200
    after_reprocess = client.get(f"/api/projects/{project_id}/stacks")
    assert after_reprocess.status_code == 200
    persisted_stack = next((item for item in after_reprocess.json()["items"] if item["id"] == new_stack_id), None)
    assert persisted_stack is not None
    assert moved_reference_id in persisted_stack["photo_ids"]

    split_again = client.post(
        f"/api/projects/{project_id}/stacks/{target['id']}/split",
        json={"reference_ids": target["photo_ids"]},
    )
    assert split_again.status_code == 400


def test_new_additions_unresolve_previous_pick(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)
    project = client.post("/api/projects", json={"name": "Review Test"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    image_a = Image.new("RGB", (40, 30), color=(40, 80, 120))
    image_b = Image.new("RGB", (40, 30), color=(45, 85, 125))
    image_c = Image.new("RGB", (40, 30), color=(40, 80, 120))
    path_a = tmp_path / "review_a.jpg"
    path_b = tmp_path / "review_b.jpg"
    path_c = tmp_path / "review_c.jpg"
    image_a.save(path_a)
    image_b.save(path_b)
    image_c.save(path_c)

    seed = client.post(
        f"/api/projects/{project_id}/intake/references",
        json={
            "items": [
                {"source": str(path_a), "source_type": "path", "label": "A", "metadata": {}},
                {"source": str(path_b), "source_type": "path", "label": "B", "metadata": {}},
            ]
        },
    )
    assert seed.status_code == 200

    process = client.post(f"/api/projects/{project_id}/process", json={})
    assert process.status_code == 200
    initial_stacks = client.get(f"/api/projects/{project_id}/stacks").json()["items"]
    target = next((item for item in initial_stacks if len(item["photo_ids"]) > 1), None)
    assert target is not None

    initial_pick = int(target["photo_ids"][0])
    pick_res = client.post(
        f"/api/projects/{project_id}/duel/pick",
        json={"stack_id": target["id"], "reference_id": initial_pick},
    )
    assert pick_res.status_code == 200

    add_ref = client.post(
        f"/api/projects/{project_id}/intake/references",
        json={"items": [{"source": str(path_c), "source_type": "path", "label": "C", "metadata": {}}]},
    )
    assert add_ref.status_code == 200
    added_ref_id = int(add_ref.json()["items"][-1]["id"])

    reprocess = client.post(f"/api/projects/{project_id}/process", json={})
    assert reprocess.status_code == 200
    stacks_after = client.get(f"/api/projects/{project_id}/stacks").json()["items"]
    reviewed = next((item for item in stacks_after if added_ref_id in item["photo_ids"]), None)
    assert reviewed is not None
    assert reviewed["needs_review"] is True
    assert reviewed["resolved"] is False
    assert reviewed["previous_pick_reference_id"] == initial_pick
    assert added_ref_id in reviewed["new_reference_ids"]


def test_reset_project_storage_tolerates_enotempty(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = projects_index.create_project("Reset Retry")
    project_id = project["id"]
    root = projects_index.get_project_root(project_id)
    (root / "originals").mkdir(parents=True, exist_ok=True)
    (root / "originals" / "x.txt").write_text("x", encoding="utf-8")

    real_rmtree = projects_index.shutil.rmtree
    state = {"calls": 0}

    def flaky_rmtree(path: Path) -> None:
        state["calls"] += 1
        if state["calls"] == 1:
            raise OSError(errno.ENOTEMPTY, "Directory not empty")
        real_rmtree(path)

    monkeypatch.setattr(projects_index.shutil, "rmtree", flaky_rmtree)

    projects_index.reset_project_storage(project_id)

    assert projects_index.get_project_root(project_id).exists()
    assert projects_index.get_project_originals_dir(project_id).exists()
    assert projects_index.get_project_derived_dir(project_id).exists()


def test_delete_project_endpoint_removes_project_and_storage(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    create = client.post("/api/projects", json={"name": "Delete Me"})
    assert create.status_code == 201
    project_id = create.json()["id"]
    project_root = projects_index.get_project_root(project_id)
    (project_root / "originals" / "marker.txt").write_text("to-delete", encoding="utf-8")

    remove = client.delete(f"/api/projects/{project_id}")
    assert remove.status_code == 200
    assert remove.json()["status"] == "ok"

    details = client.get(f"/api/projects/{project_id}")
    assert details.status_code == 404

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert all(item["id"] != project_id for item in listed.json()["items"])
    assert not project_root.exists()

    remove_again = client.delete(f"/api/projects/{project_id}")
    assert remove_again.status_code == 404


def test_stack_ignore_and_delete_endpoints(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    project = client.post("/api/projects", json={"name": "Stack Actions"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    image_a = Image.new("RGB", (40, 30), color=(12, 44, 99))
    image_b = Image.new("RGB", (40, 30), color=(12, 44, 99))
    path_a = tmp_path / "stack_action_a.jpg"
    path_b = tmp_path / "stack_action_b.jpg"
    image_a.save(path_a)
    image_b.save(path_b)

    seed = client.post(
        f"/api/projects/{project_id}/intake/references",
        json={
            "items": [
                {"source": str(path_a), "source_type": "path", "label": "A", "metadata": {}},
                {"source": str(path_b), "source_type": "path", "label": "B", "metadata": {}},
            ]
        },
    )
    assert seed.status_code == 200

    process = client.post(f"/api/projects/{project_id}/process", json={})
    assert process.status_code == 200
    stacks = client.get(f"/api/projects/{project_id}/stacks")
    assert stacks.status_code == 200
    items = stacks.json()["items"]
    assert items
    target = items[0]
    stack_id = str(target["id"])
    reference_ids = [int(item) for item in target["photo_ids"]]

    ignored = client.post(
        f"/api/projects/{project_id}/stacks/{stack_id}/ignore",
        json={"ignored": True},
    )
    assert ignored.status_code == 200
    ignored_item = next((item for item in ignored.json()["items"] if str(item["id"]) == stack_id), None)
    assert ignored_item is not None
    assert ignored_item["ignored"] is True

    unignored = client.post(
        f"/api/projects/{project_id}/stacks/{stack_id}/ignore",
        json={"ignored": False},
    )
    assert unignored.status_code == 200
    unignored_item = next((item for item in unignored.json()["items"] if str(item["id"]) == stack_id), None)
    assert unignored_item is not None
    assert unignored_item["ignored"] is False

    deleted = client.delete(f"/api/projects/{project_id}/stacks/{stack_id}")
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload["status"] == "ok"
    assert payload["deleted"]["stack_id"] == stack_id
    assert payload["deleted"]["references"] >= 1

    stacks_after = payload["items"]
    assert all(str(item["id"]) != stack_id for item in stacks_after)

    refs_after = client.get(f"/api/projects/{project_id}/intake/references")
    assert refs_after.status_code == 200
    remaining_ids = {int(item["id"]) for item in refs_after.json()["items"]}
    assert all(ref_id not in remaining_ids for ref_id in reference_ids)

    # At least one source file from the deleted stack should be removed from disk.
    assert not (path_a.exists() and path_b.exists())


def test_theme_description_can_be_updated(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    project = client.post("/api/projects", json={"name": "Theme Description"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    themes_before = client.get(f"/api/projects/{project_id}/themes")
    assert themes_before.status_code == 200
    theme_id = themes_before.json()["items"][0]["id"]

    patch = client.patch(
        f"/api/projects/{project_id}/themes/{theme_id}",
        json={"description": "City mornings and street life"},
    )
    assert patch.status_code == 200
    assert patch.json()["description"] == "City mornings and street life"

    themes_after = client.get(f"/api/projects/{project_id}/themes")
    assert themes_after.status_code == 200
    updated = next((item for item in themes_after.json()["items"] if item["id"] == theme_id), None)
    assert updated is not None
    assert updated["description"] == "City mornings and street life"


def test_reassign_themes_endpoint_exists(tmp_path, monkeypatch) -> None:
    client = _project_client(tmp_path, monkeypatch)

    project = client.post("/api/projects", json={"name": "Theme Reassign"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    res = client.post(f"/api/projects/{project_id}/themes/reassign")
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert "summary" in payload
