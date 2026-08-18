"""End-to-end test for the processing flow.

Uploads the vacation-20 fixture pack, receives the automatic process job, polls
to completion, and asserts the resulting stacks/themes are well-formed.
This is the M1 integration heartbeat — if this test goes red, the
backend story is broken.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from shoebox.pipeline import tier1


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

    job_id = upload["job_id"]
    assert job_id is not None
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

    upload = _upload_all(client, project_id, fixture_pack_dir)
    job_id = upload["job_id"]
    assert job_id is not None
    assert _wait_for_job(client, job_id)["status"] == "completed"

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
    upload = _upload_all(client, project_id, fixture_pack_dir)
    first_job_id = upload["job_id"]
    assert first_job_id is not None
    assert _wait_for_job(client, first_job_id)["status"] == "completed"
    first_stacks = client.get(f"/api/projects/{project_id}/stacks").json()

    second_job = client.post(f"/api/projects/{project_id}/process").json()
    assert _wait_for_job(client, second_job["id"])["status"] == "completed"
    second_stacks = client.get(f"/api/projects/{project_id}/stacks").json()

    # Same input → same shape (count and sizes).
    assert len(first_stacks) == len(second_stacks)
    assert sorted(len(s["reference_ids"]) for s in first_stacks) == sorted(
        len(s["reference_ids"]) for s in second_stacks
    )


def test_renaming_a_theme_persists(client: TestClient, fixture_pack_dir: Path) -> None:
    project = client.post("/api/projects", json={"name": "Rename"}).json()
    project_id = project["id"]
    upload = _upload_all(client, project_id, fixture_pack_dir)
    job_id = upload["job_id"]
    assert job_id is not None
    assert _wait_for_job(client, job_id)["status"] == "completed"

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

    upload = _upload_all(client, project_id, fixture_pack_dir)
    job_id = upload["job_id"]
    assert job_id is not None
    assert _wait_for_job(client, job_id)["status"] == "completed"

    reprocessing = client.post(f"/api/projects/{project_id}/process").json()
    assert _wait_for_job(client, reprocessing["id"])["status"] == "completed"

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
    upload = _upload_all(client, project_id, fixture_pack_dir)
    first_job = upload["job_id"]
    assert first_job is not None
    assert _wait_for_job(client, first_job)["status"] == "completed"

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    assert themes, "expected at least one auto-proposed theme after first processing"
    chosen_id = themes[0]["id"]

    renamed = client.patch(f"/api/themes/{chosen_id}", json={"name": "Sunset Walks"})
    assert renamed.status_code == 200

    second_job = client.post(f"/api/projects/{project_id}/process").json()["id"]
    assert _wait_for_job(client, second_job)["status"] == "completed"

    themes_after = client.get(f"/api/projects/{project_id}/themes").json()
    surviving = [t for t in themes_after if t["id"] == chosen_id]
    assert surviving, "Renamed theme was wiped by reprocessing."
    assert surviving[0]["name"] == "Sunset Walks"


def _upload_some(
    client: TestClient, project_id: str, fixture_dir: Path, names: list[str]
) -> dict:
    files = []
    handles = []
    try:
        for name in names:
            path = fixture_dir / name
            handle = path.open("rb")
            handles.append(handle)
            files.append(("files", (path.name, handle, "image/jpeg")))
        response = client.post(f"/api/projects/{project_id}/uploads", files=files)
    finally:
        for handle in handles:
            handle.close()
    assert response.status_code == 201
    return response.json()


def test_curated_theme_assignments_survive_a_later_upload(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    """The reported bug: adding photos scattered already-filed stacks.

    Processing used to wipe and recreate every stack, cascading
    ``stack_themes`` away, so a fresh upload re-shuffled the owner's
    curation. Whatever the owner filed must stay filed.
    """
    project = client.post("/api/projects", json={"name": "Incremental"}).json()
    project_id = project["id"]

    photos = sorted(p.name for p in fixture_pack_dir.glob("vacation_*.jpg"))
    first_batch, second_batch = photos[:10], photos[10:]

    upload = _upload_some(client, project_id, fixture_pack_dir, first_batch)
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    curated = client.post(
        f"/api/projects/{project_id}/themes", json={"name": "Best of the trip"}
    ).json()
    stacks = client.get(f"/api/projects/{project_id}/stacks").json()
    assert len(stacks) >= 3
    filed = [s["id"] for s in stacks[:3]]
    for stack_id in filed:
        assert (
            client.post(
                f"/api/themes/{curated['id']}/assign", json={"stack_id": stack_id}
            ).status_code
            == 204
        )

    second = _upload_some(client, project_id, fixture_pack_dir, second_batch)
    assert second["accepted"] == len(second_batch)
    assert _wait_for_job(client, second["job_id"])["status"] == "completed"

    still_filed = client.get(f"/api/themes/{curated['id']}/stacks").json()
    assert sorted(still_filed) == sorted(filed), (
        "Uploading more photos moved stacks out of the theme the owner chose."
    )


def test_a_manual_move_is_not_undone_by_reprocessing(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Manual move"}).json()
    project_id = project["id"]
    upload = _upload_all(client, project_id, fixture_pack_dir)
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    source = client.get(f"/api/projects/{project_id}/themes").json()[0]
    target = client.post(
        f"/api/projects/{project_id}/themes", json={"name": "Keepers"}
    ).json()
    moving = client.get(f"/api/themes/{source['id']}/stacks").json()[0]

    assert (
        client.post(
            f"/api/themes/{target['id']}/assign", json={"stack_id": moving}
        ).status_code
        == 204
    )

    reprocess = client.post(f"/api/projects/{project_id}/process").json()
    assert _wait_for_job(client, reprocess["id"])["status"] == "completed"

    assert moving in client.get(f"/api/themes/{target['id']}/stacks").json()
    assert moving not in client.get(f"/api/themes/{source['id']}/stacks").json()


def test_deleting_a_theme_removes_it_and_its_pages(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Delete theme"}).json()
    project_id = project["id"]
    upload = _upload_all(client, project_id, fixture_pack_dir)
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    theme = client.get(f"/api/projects/{project_id}/themes").json()[0]
    page = client.post(f"/api/themes/{theme['id']}/pages", json={}).json()

    assert client.delete(f"/api/themes/{theme['id']}").status_code == 204

    remaining = client.get(f"/api/projects/{project_id}/themes").json()
    assert all(t["id"] != theme["id"] for t in remaining)
    assert client.get(f"/api/pages/{page['id']}/items").status_code == 404
    assert client.delete(f"/api/themes/{theme['id']}").status_code == 404
    # The photos themselves are untouched.
    assert client.get(f"/api/projects/{project_id}/stacks").json()


def test_deleting_a_page_leaves_the_theme_intact(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Delete page"}).json()
    project_id = project["id"]
    upload = _upload_all(client, project_id, fixture_pack_dir)
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    theme = client.get(f"/api/projects/{project_id}/themes").json()[0]
    first = client.post(f"/api/themes/{theme['id']}/pages", json={}).json()
    second = client.post(f"/api/themes/{theme['id']}/pages", json={}).json()

    assert client.delete(f"/api/pages/{first['id']}").status_code == 204

    pages = client.get(f"/api/themes/{theme['id']}/pages").json()
    assert [p["id"] for p in pages] == [second["id"]]
    assert pages[0]["order_index"] == 0
    assert client.delete(f"/api/pages/{first['id']}").status_code == 404


HOME = (55.6761, 12.5683)
ACROSS_TOWN = (55.7061, 12.5683)  # ~3.3 km away, past the 2 km default
THE_HARBOUR = (55.6461, 12.5683)  # ~3.3 km the other way


def _stub_exif(
    monkeypatch: pytest.MonkeyPatch,
    plan: list[tuple[str, tuple[float, float]]],
) -> None:
    """Hand the next uploads the listed capture times and locations.

    The fixture pack carries no EXIF at all, so location behaviour has to
    be injected. Tier-1 reads the datetime and then the GPS of each file
    in turn, so one cursor drives both.
    """
    cursor = {"i": -1}

    def fake_datetime(image: Image.Image) -> str | None:
        cursor["i"] += 1
        return plan[cursor["i"]][0]

    def fake_gps(image: Image.Image) -> tuple[float | None, float | None]:
        return plan[cursor["i"]][1]

    monkeypatch.setattr(tier1, "_exif_datetime", fake_datetime)
    monkeypatch.setattr(tier1, "_exif_gps", fake_gps)


def test_same_day_photos_at_two_locations_get_two_themes(
    client: TestClient, fixture_pack_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the GPS split used to be undone by theme naming.

    ``propose_themes`` splits a day that moves 3 km, but both proposals
    are named after the same date, and ``process_project`` used to let
    one theme absorb every proposal sharing its name — collapsing the
    split back into a single theme. Each existing theme may now absorb
    at most one proposal.
    """
    project = client.post("/api/projects", json={"name": "Two places"}).json()
    project_id = project["id"]

    _stub_exif(
        monkeypatch,
        [
            ("2026-04-01T09:00:00", HOME),
            ("2026-04-01T09:30:00", HOME),
            ("2026-04-01T10:00:00", ACROSS_TOWN),
            ("2026-04-01T10:30:00", ACROSS_TOWN),
        ],
    )
    upload = _upload_some(
        client,
        project_id,
        fixture_pack_dir,
        ["vacation_01.jpg", "vacation_02.jpg", "vacation_03.jpg", "vacation_04.jpg"],
    )
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    assert [t["name"] for t in themes] == ["Apr 1, 2026", "Apr 1, 2026 (2)"], (
        "The two locations were collapsed back into one theme."
    )


def test_reprocessing_an_already_split_day_leaves_its_themes_untouched(
    client: TestClient, fixture_pack_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consuming a theme per proposal must not cost idempotency.

    Note what this does *not* cover: every stack is already filed by the
    second run, so no proposals are generated and the naming path is
    never reached. Duplicate names are the job of
    ``test_a_theme_absorbed_by_a_proposal_keeps_its_name_reserved``.
    """
    project = client.post("/api/projects", json={"name": "Two places twice"}).json()
    project_id = project["id"]

    _stub_exif(
        monkeypatch,
        [
            ("2026-04-01T09:00:00", HOME),
            ("2026-04-01T10:00:00", ACROSS_TOWN),
        ],
    )
    upload = _upload_some(
        client, project_id, fixture_pack_dir, ["vacation_01.jpg", "vacation_02.jpg"]
    )
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"
    first = client.get(f"/api/projects/{project_id}/themes").json()

    reprocess = client.post(f"/api/projects/{project_id}/process").json()
    assert _wait_for_job(client, reprocess["id"])["status"] == "completed"
    second = client.get(f"/api/projects/{project_id}/themes").json()

    assert [t["name"] for t in second] == [t["name"] for t in first]
    assert [t["id"] for t in second] == [t["id"] for t in first]


def test_a_theme_absorbed_by_a_proposal_keeps_its_name_reserved(
    client: TestClient, fixture_pack_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absorbing a theme must not release its name back into the pool.

    A theme that absorbs a proposal leaves the mergeable set but still
    exists under its name. If that name is not reserved, a second
    proposal for the same day creates a *second* theme called
    ``Apr 1, 2026`` — ``themes.name`` has no UNIQUE constraint, so the
    duplicate lands silently and the owner sees the same name twice.
    """
    project = client.post("/api/projects", json={"name": "Absorb then split"}).json()
    project_id = project["id"]

    _stub_exif(monkeypatch, [("2026-04-01T09:00:00", HOME)])
    first = _upload_some(client, project_id, fixture_pack_dir, ["vacation_01.jpg"])
    assert _wait_for_job(client, first["job_id"])["status"] == "completed"
    assert [t["name"] for t in client.get(f"/api/projects/{project_id}/themes").json()] == [
        "Apr 1, 2026"
    ]

    # Same day, two further locations: two proposals, one shared base name.
    _stub_exif(
        monkeypatch,
        [
            ("2026-04-01T11:00:00", ACROSS_TOWN),
            ("2026-04-01T12:00:00", THE_HARBOUR),
        ],
    )
    second = _upload_some(
        client, project_id, fixture_pack_dir, ["vacation_05.jpg", "vacation_06.jpg"]
    )
    assert _wait_for_job(client, second["job_id"])["status"] == "completed"

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    names = [t["name"] for t in themes]
    assert len(set(names)) == len(names), f"two themes share a name: {names}"
    assert names == ["Apr 1, 2026", "Apr 1, 2026 (2)"]


def test_an_owner_named_theme_is_never_absorbed_by_a_proposal(
    client: TestClient, fixture_pack_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An owner's theme only reserves its name; proposals route around it."""
    project = client.post("/api/projects", json={"name": "Reserved name"}).json()
    project_id = project["id"]
    owned = client.post(
        f"/api/projects/{project_id}/themes", json={"name": "Apr 1, 2026"}
    ).json()

    _stub_exif(monkeypatch, [("2026-04-01T09:00:00", HOME)])
    upload = _upload_some(client, project_id, fixture_pack_dir, ["vacation_01.jpg"])
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    themes = client.get(f"/api/projects/{project_id}/themes").json()
    assert [t["name"] for t in themes] == ["Apr 1, 2026", "Apr 1, 2026 (2)"]
    # The owner's theme keeps its name and stays empty.
    assert client.get(f"/api/themes/{owned['id']}/stacks").json() == []


def test_unassigning_a_stack_frees_it_from_its_theme(
    client: TestClient, fixture_pack_dir: Path
) -> None:
    project = client.post("/api/projects", json={"name": "Unassign"}).json()
    project_id = project["id"]
    upload = _upload_all(client, project_id, fixture_pack_dir)
    assert _wait_for_job(client, upload["job_id"])["status"] == "completed"

    theme = client.get(f"/api/projects/{project_id}/themes").json()[0]
    stack_id = client.get(f"/api/themes/{theme['id']}/stacks").json()[0]

    assert client.delete(f"/api/themes/{theme['id']}/stacks/{stack_id}").status_code == 204
    assert stack_id not in client.get(f"/api/themes/{theme['id']}/stacks").json()
    assert client.delete(f"/api/themes/{theme['id']}/stacks/{stack_id}").status_code == 404
