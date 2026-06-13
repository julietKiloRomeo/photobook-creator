"""Tests for the persistence layer.

These assert *intent*:
- creating things makes them appear in listings;
- duplicate uploads deduplicate;
- single-photo stacks resolve themselves;
- relationships (theme/stack, page/item) round-trip.

No test asserts on internal ID shapes, response key spellings, or SQL
specifics. If we swapped SQLite for Postgres tomorrow these tests
should still pass unchanged.
"""

from __future__ import annotations

import json

import pytest
from shoebox.config import Settings
from shoebox.store import connection, dao, initialise


@pytest.fixture()
def conn(settings: Settings):
    initialise()
    with connection() as c:
        yield c


def test_project_create_list_delete_roundtrip(conn) -> None:
    project = dao.create_project(conn, name="Italy 2026")
    assert project["name"] == "Italy 2026"

    listed = dao.list_projects(conn)
    assert any(p["id"] == project["id"] for p in listed)

    deleted = dao.delete_project(conn, project["id"])
    assert deleted is True
    assert dao.get_project(conn, project["id"]) is None


def test_uploading_the_same_bytes_twice_yields_one_reference(conn) -> None:
    project = dao.create_project(conn, name="Dedup")

    first = dao.upsert_reference(
        conn,
        project_id=project["id"],
        original_path="/photos/a.jpg",
        file_hash="abc123",
    )
    second = dao.upsert_reference(
        conn,
        project_id=project["id"],
        original_path="/photos/b.jpg",  # different path
        file_hash="abc123",  # same bytes
    )

    assert first["id"] == second["id"]
    assert len(dao.list_references(conn, project["id"])) == 1


def test_single_photo_stack_resolves_itself(conn) -> None:
    project = dao.create_project(conn, name="Solo")
    ref = dao.upsert_reference(
        conn,
        project_id=project["id"],
        original_path="/p/solo.jpg",
        file_hash="solohash",
    )

    stack = dao.create_stack(conn, project_id=project["id"], reference_ids=[ref["id"]])

    assert stack["status"] == "resolved"
    assert stack["picked_reference_id"] == ref["id"]


def test_multi_photo_stack_starts_pending_and_can_be_picked(conn) -> None:
    project = dao.create_project(conn, name="Burst")
    ref_ids = [
        dao.upsert_reference(
            conn, project_id=project["id"], original_path=f"/p/{i}.jpg", file_hash=f"h{i}"
        )["id"]
        for i in range(3)
    ]

    stack = dao.create_stack(conn, project_id=project["id"], reference_ids=ref_ids)
    assert stack["status"] == "pending"
    assert stack["picked_reference_id"] is None
    assert set(stack["reference_ids"]) == set(ref_ids)

    updated = dao.update_stack(
        conn, stack["id"], picked_reference_id=ref_ids[1], status="resolved"
    )
    assert updated is not None
    assert updated["picked_reference_id"] == ref_ids[1]
    assert updated["status"] == "resolved"


def test_list_stacks_can_filter_by_status(conn) -> None:
    project = dao.create_project(conn, name="Filter")
    a = dao.upsert_reference(conn, project_id=project["id"], original_path="/a.jpg", file_hash="a")
    b = dao.upsert_reference(conn, project_id=project["id"], original_path="/b.jpg", file_hash="b")
    c = dao.upsert_reference(conn, project_id=project["id"], original_path="/c.jpg", file_hash="c")

    dao.create_stack(conn, project_id=project["id"], reference_ids=[a["id"]])  # auto-resolved
    pending = dao.create_stack(conn, project_id=project["id"], reference_ids=[b["id"], c["id"]])

    pending_stacks = dao.list_stacks(conn, project["id"], status="pending")
    resolved_stacks = dao.list_stacks(conn, project["id"], status="resolved")

    assert [s["id"] for s in pending_stacks] == [pending["id"]]
    assert len(resolved_stacks) == 1


def test_theme_assignment_is_exclusive_by_default(conn) -> None:
    project = dao.create_project(conn, name="Themes")
    ref = dao.upsert_reference(
        conn, project_id=project["id"], original_path="/x.jpg", file_hash="x"
    )
    stack = dao.create_stack(conn, project_id=project["id"], reference_ids=[ref["id"]])

    theme_a = dao.create_theme(conn, project_id=project["id"], name="Morning")
    theme_b = dao.create_theme(conn, project_id=project["id"], name="Evening")

    dao.assign_stack_to_theme(conn, stack_id=stack["id"], theme_id=theme_a["id"])
    assert dao.list_stack_ids_for_theme(conn, theme_a["id"]) == [stack["id"]]

    dao.assign_stack_to_theme(conn, stack_id=stack["id"], theme_id=theme_b["id"])
    assert dao.list_stack_ids_for_theme(conn, theme_a["id"]) == []
    assert dao.list_stack_ids_for_theme(conn, theme_b["id"]) == [stack["id"]]


def test_theme_order_index_auto_increments(conn) -> None:
    project = dao.create_project(conn, name="Ordered")
    first = dao.create_theme(conn, project_id=project["id"], name="A")
    second = dao.create_theme(conn, project_id=project["id"], name="B")
    third = dao.create_theme(conn, project_id=project["id"], name="C")
    assert first["order_index"] < second["order_index"] < third["order_index"]


def test_pages_and_items_round_trip(conn) -> None:
    project = dao.create_project(conn, name="Book")
    theme = dao.create_theme(conn, project_id=project["id"], name="Day 1")
    ref = dao.upsert_reference(
        conn,
        project_id=project["id"],
        original_path="/p/1.jpg",
        file_hash="1",
        width=4000,
        height=3000,
    )

    page = dao.create_page(conn, theme_id=theme["id"])
    photo_item = dao.add_page_item(
        conn,
        page_id=page["id"],
        kind="photo",
        slot_index=0,
        reference_id=ref["id"],
        position_json=json.dumps({"x": 0, "y": 0, "w": 0.5, "h": 0.5}),
    )
    text_item = dao.add_page_item(
        conn,
        page_id=page["id"],
        kind="text",
        slot_index=1,
        text_content="Hello",
    )

    items = dao.list_page_items(conn, page["id"])
    assert {it["id"] for it in items} == {photo_item["id"], text_item["id"]}

    dao.delete_page_item(conn, photo_item["id"])
    remaining = dao.list_page_items(conn, page["id"])
    assert [it["id"] for it in remaining] == [text_item["id"]]


def test_page_item_kinds_are_validated(conn) -> None:
    project = dao.create_project(conn, name="Validate")
    theme = dao.create_theme(conn, project_id=project["id"], name="X")
    page = dao.create_page(conn, theme_id=theme["id"])

    with pytest.raises(ValueError):
        dao.add_page_item(conn, page_id=page["id"], kind="video", slot_index=0)

    with pytest.raises(ValueError):
        dao.add_page_item(conn, page_id=page["id"], kind="photo", slot_index=0)

    with pytest.raises(ValueError):
        dao.add_page_item(conn, page_id=page["id"], kind="text", slot_index=0)


def test_jobs_track_progress_and_completion(conn) -> None:
    project = dao.create_project(conn, name="Job")
    job = dao.create_job(conn, project_id=project["id"], kind="process")
    assert job["status"] == "queued"
    assert job["progress"] == 0.0

    dao.update_job(conn, job["id"], status="running", progress=0.5, message="halfway", started=True)
    mid = dao.get_job(conn, job["id"])
    assert mid is not None
    assert mid["status"] == "running"
    assert mid["progress"] == pytest.approx(0.5)
    assert mid["started_at"] is not None

    dao.update_job(conn, job["id"], status="completed", progress=1.0, finished=True)
    done = dao.get_job(conn, job["id"])
    assert done is not None
    assert done["status"] == "completed"
    assert done["finished_at"] is not None


def test_replace_stacks_swaps_in_a_new_grouping(conn) -> None:
    project = dao.create_project(conn, name="Recluster")
    refs = [
        dao.upsert_reference(
            conn, project_id=project["id"], original_path=f"/{i}.jpg", file_hash=f"h{i}"
        )["id"]
        for i in range(4)
    ]
    # Initial: each photo in its own stack.
    for ref_id in refs:
        dao.create_stack(conn, project_id=project["id"], reference_ids=[ref_id])
    assert len(dao.list_stacks(conn, project["id"])) == 4

    dao.replace_stacks(conn, project["id"], [refs[:2], refs[2:]])
    after = dao.list_stacks(conn, project["id"])
    assert len(after) == 2
    sizes = sorted(len(s["reference_ids"]) for s in after)
    assert sizes == [2, 2]


def test_deleting_a_project_cascades_to_its_data(conn) -> None:
    project = dao.create_project(conn, name="Cascade")
    ref = dao.upsert_reference(
        conn, project_id=project["id"], original_path="/c.jpg", file_hash="c"
    )
    stack = dao.create_stack(conn, project_id=project["id"], reference_ids=[ref["id"]])
    theme = dao.create_theme(conn, project_id=project["id"], name="T")
    dao.assign_stack_to_theme(conn, stack_id=stack["id"], theme_id=theme["id"])
    page = dao.create_page(conn, theme_id=theme["id"])
    dao.add_page_item(conn, page_id=page["id"], kind="text", slot_index=0, text_content="hi")

    dao.delete_project(conn, project["id"])

    assert dao.list_references(conn, project["id"]) == []
    assert dao.list_stacks(conn, project["id"]) == []
    assert dao.list_themes(conn, project["id"]) == []
