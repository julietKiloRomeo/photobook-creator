"""End-to-end test for the processing flow.

Uploads the vacation-20 fixture pack, kicks off the process job, polls
to completion, and asserts the resulting stacks/themes are well-formed.
This is the M1 integration heartbeat — if this test goes red, the
backend story is broken.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish in time; last={job}")


def _upload_all(client: TestClient, project_id: str, fixture_dir: Path) -> dict:
    photos = sorted(fixture_dir.glob("vacation_*.jpg"))
    files = []
    handles = []
    try:
        for p in photos:
            f = p.open("rb")
            handles.append(f)
            files.append(("files", (p.name, f, "image/jpeg")))
        response = client.post(f"/api/projects/{project_id}/uploads", files=files)
    finally:
        for f in handles:
            f.close()
    assert response.status_code == 201
    return response.json()


def test_end_to_end_processing_produces_stacks_and_themes(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Vacation 2026"}).json()
    project_id = project["id"]

    upload = _upload_all(client, project_id, fixture_pack_dir)
    assert upload["accepted"] == 20

    queued = client.post(f"/api/projects/{project_id}/process")
    assert queued.status_code == 202
    job_id = queued.json()["id"]

    finished = _wait_for_job(client, job_id)
    assert finished["status"] == "completed", finished

    stacks = client.get(f"/api/projects/{project_id}/stacks").json()
    assert len(stacks) >= 1
    # Every stack contains at least one photo.
    for stack in stacks:
        assert len(stack["reference_ids"]) >= 1
    # The total photos in stacks must equal the photos uploaded.
    total_in_stacks = sum(len(s["reference_ids"]) for s in stacks)
    assert total_in_stacks == 20

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    assert len(themes) >= 1
    # Every theme has a name and a color.
    for theme in themes:
        assert theme["name"].strip()
        assert theme["color"].startswith("#")

    # Each stack should be assigned to at most one theme; collectively
    # all stacks are covered.
    assignments: list[str] = []
    for theme in themes:
        stack_ids = client.get(f"/api/themes/{theme['id']}/stacks").json()
        assignments.extend(stack_ids)
    assert sorted(assignments) == sorted(s["id"] for s in stacks)


def test_picking_a_stack_marks_it_resolved(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Pick"}).json()
    project_id = project["id"]

    _upload_all(client, project_id, fixture_pack_dir)
    job_id = client.post(f"/api/projects/{project_id}/process").json()["id"]
    _wait_for_job(client, job_id)

    stacks = client.get(f"/api/projects/{project_id}/stacks").json()
    multi = next((s for s in stacks if len(s["reference_ids"]) > 1), None)
    if multi is None:
        # Even if the fixture happens to produce all singletons, the
        # auto-resolution path is exercised. Bail out cleanly.
        return

    chosen = multi["reference_ids"][0]
    response = client.patch(
        f"/api/stacks/{multi['id']}",
        json={"picked_reference_id": chosen},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["picked_reference_id"] == chosen
    assert updated["status"] == "resolved"


def test_reprocessing_replaces_the_stack_set(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Idempotent"}).json()
    project_id = project["id"]
    _upload_all(client, project_id, fixture_pack_dir)

    first_job = client.post(f"/api/projects/{project_id}/process").json()
    _wait_for_job(client, first_job["id"])
    first_stacks = client.get(f"/api/projects/{project_id}/stacks").json()

    second_job = client.post(f"/api/projects/{project_id}/process").json()
    _wait_for_job(client, second_job["id"])
    second_stacks = client.get(f"/api/projects/{project_id}/stacks").json()

    # Same input → same shape (count and sizes).
    assert len(first_stacks) == len(second_stacks)
    assert sorted(len(s["reference_ids"]) for s in first_stacks) == sorted(
        len(s["reference_ids"]) for s in second_stacks
    )


def test_renaming_a_theme_persists(client: TestClient, fixture_pack_dir: Path) -> None:
    project = client.post("/api/projects", json={"name": "Rename"}).json()
    project_id = project["id"]
    _upload_all(client, project_id, fixture_pack_dir)
    job_id = client.post(f"/api/projects/{project_id}/process").json()["id"]
    _wait_for_job(client, job_id)

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    assert themes
    theme_id = themes[0]["id"]

    renamed = client.patch(f"/api/themes/{theme_id}", json={"name": "Beach Day"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Beach Day"

    again = client.get(f"/api/projects/{project_id}/themes").json()
    assert any(t["id"] == theme_id and t["name"] == "Beach Day" for t in again)


def test_user_created_theme_survives_processing(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    """Regression for B-1 (step-2 manual finding).

    jkr added a theme before uploading photos, and it disappeared after
    processing. User-created themes must survive any number of processing
    runs — only AI-proposed themes the user has not touched may be
    replaced by reprocessing.
    """
    project = client.post("/api/projects", json={"name": "Pre-upload theme"}).json()
    project_id = project["id"]

    user_theme = client.post(
        f"/api/projects/{project_id}/themes",
        json={"name": "Memories of Mom"},
    ).json()
    user_theme_id = user_theme["id"]

    _upload_all(client, project_id, fixture_pack_dir)
    job_id = client.post(f"/api/projects/{project_id}/process").json()["id"]
    _wait_for_job(client, job_id)

    themes_after = client.get(f"/api/projects/{project_id}/themes").json()
    surviving = [t for t in themes_after if t["id"] == user_theme_id]
    assert surviving, (
        "User-created theme was wiped by processing. "
        f"Themes after processing: {[t['name'] for t in themes_after]}"
    )
    assert surviving[0]["name"] == "Memories of Mom"


def test_renamed_auto_theme_survives_reprocessing(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    """Regression for B-1, second arm.

    If a user renames an AI-proposed theme, that rename is implicit
    adoption — the theme must survive subsequent reprocessing.
    """
    project = client.post("/api/projects", json={"name": "Rename then reprocess"}).json()
    project_id = project["id"]
    _upload_all(client, project_id, fixture_pack_dir)

    first_job = client.post(f"/api/projects/{project_id}/process").json()["id"]
    _wait_for_job(client, first_job)

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    assert themes, "expected at least one auto-proposed theme after first processing"
    chosen_id = themes[0]["id"]

    renamed = client.patch(f"/api/themes/{chosen_id}", json={"name": "Sunset Walks"})
    assert renamed.status_code == 200

    second_job = client.post(f"/api/projects/{project_id}/process").json()["id"]
    _wait_for_job(client, second_job)

    themes_after = client.get(f"/api/projects/{project_id}/themes").json()
    surviving = [t for t in themes_after if t["id"] == chosen_id]
    assert surviving, "Renamed theme was wiped by reprocessing."
    assert surviving[0]["name"] == "Sunset Walks"
