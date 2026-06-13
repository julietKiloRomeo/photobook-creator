"""DAO: thin, explicit SQL functions keyed by entity.

These are deliberately not abstracted into a Repository class. Each
function does one thing, takes a sqlite3.Connection, and returns dicts
(via sqlite3.Row).

The function names use the entity in the verb so call sites read like
prose: ``create_project(conn, name="...")``,
``list_pending_stacks(conn, project_id)``.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- projects --

def create_project(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    project_id = _new_id("p")
    conn.execute(
        "INSERT INTO projects (id, name, created_at, status) VALUES (?, ?, ?, 'active')",
        (project_id, name, _now_iso()),
    )
    fetched = get_project(conn, project_id)
    assert fetched is not None
    return fetched


def get_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    return _row(cur.fetchone())


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute("SELECT * FROM projects ORDER BY created_at DESC")
    return _rows(cur.fetchall())


def delete_project(conn: sqlite3.Connection, project_id: str) -> bool:
    cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return cur.rowcount > 0


# -------------------------------------------------------------- references --

def upsert_reference(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    original_path: str,
    file_hash: str,
    phash: str | None = None,
    captured_at: str | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    width: int | None = None,
    height: int | None = None,
    uploader_member_id: str | None = None,
) -> dict[str, Any]:
    """Insert a reference if its (project_id, file_hash) is new, else return existing.

    The dedup contract is: identical bytes anywhere in the same project
    are a single reference. Callers don't have to check first.
    """
    existing = conn.execute(
        "SELECT * FROM references_ WHERE project_id = ? AND file_hash = ?",
        (project_id, file_hash),
    ).fetchone()
    if existing is not None:
        return dict(existing)

    reference_id = _new_id("r")
    conn.execute(
        """
        INSERT INTO references_ (
            id, project_id, original_path, file_hash, phash, captured_at,
            gps_lat, gps_lon, width, height, uploader_member_id, uploaded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reference_id,
            project_id,
            original_path,
            file_hash,
            phash,
            captured_at,
            gps_lat,
            gps_lon,
            width,
            height,
            uploader_member_id,
            _now_iso(),
        ),
    )
    fetched = get_reference(conn, reference_id)
    assert fetched is not None
    return fetched


def get_reference(conn: sqlite3.Connection, reference_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM references_ WHERE id = ?", (reference_id,))
    return _row(cur.fetchone())


def list_references(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM references_ WHERE project_id = ? ORDER BY captured_at ASC, uploaded_at ASC",
        (project_id,),
    )
    return _rows(cur.fetchall())


# ------------------------------------------------------------------ stacks --

def create_stack(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    reference_ids: list[str],
    picked_reference_id: str | None = None,
    status: str = "pending",
) -> dict[str, Any]:
    if not reference_ids:
        raise ValueError("A stack must contain at least one reference.")

    stack_id = _new_id("s")
    # Single-photo stacks resolve themselves immediately.
    if len(reference_ids) == 1 and picked_reference_id is None:
        picked_reference_id = reference_ids[0]
        status = "resolved"

    conn.execute(
        """
        INSERT INTO stacks (id, project_id, picked_reference_id, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (stack_id, project_id, picked_reference_id, status, _now_iso()),
    )
    conn.executemany(
        "INSERT INTO stack_references (stack_id, reference_id) VALUES (?, ?)",
        [(stack_id, ref_id) for ref_id in reference_ids],
    )
    fetched = get_stack(conn, stack_id)
    assert fetched is not None
    return fetched


def get_stack(conn: sqlite3.Connection, stack_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM stacks WHERE id = ?", (stack_id,))
    row = cur.fetchone()
    if row is None:
        return None
    stack = dict(row)
    refs = conn.execute(
        "SELECT reference_id FROM stack_references WHERE stack_id = ?",
        (stack_id,),
    ).fetchall()
    stack["reference_ids"] = [r["reference_id"] for r in refs]
    return stack


def list_stacks(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    if status is None:
        cur = conn.execute(
            "SELECT * FROM stacks WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM stacks WHERE project_id = ? AND status = ? ORDER BY created_at ASC",
            (project_id, status),
        )
    stacks = _rows(cur.fetchall())
    if not stacks:
        return []
    ids = tuple(s["id"] for s in stacks)
    placeholders = ",".join(["?"] * len(ids))
    rel = conn.execute(
        f"SELECT stack_id, reference_id FROM stack_references WHERE stack_id IN ({placeholders})",
        ids,
    ).fetchall()
    by_stack: dict[str, list[str]] = {sid: [] for sid in ids}
    for row in rel:
        by_stack[row["stack_id"]].append(row["reference_id"])
    for s in stacks:
        s["reference_ids"] = by_stack.get(s["id"], [])
    return stacks


def update_stack(
    conn: sqlite3.Connection,
    stack_id: str,
    *,
    picked_reference_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if picked_reference_id is not None:
        fields.append("picked_reference_id = ?")
        values.append(picked_reference_id)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if not fields:
        return get_stack(conn, stack_id)
    values.append(stack_id)
    conn.execute(f"UPDATE stacks SET {', '.join(fields)} WHERE id = ?", values)
    return get_stack(conn, stack_id)


def replace_stacks(
    conn: sqlite3.Connection,
    project_id: str,
    groups: list[list[str]],
) -> list[dict[str, Any]]:
    """Replace the stack set for a project. Used by the tier-2 pipeline.

    Any owner-confirmed picks for stacks that map to a new stack would
    be lost here; preserving them is M3 work, not M1.
    """
    conn.execute("DELETE FROM stacks WHERE project_id = ?", (project_id,))
    return [
        create_stack(conn, project_id=project_id, reference_ids=group)
        for group in groups
    ]


# ------------------------------------------------------------------ themes --

def create_theme(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    name: str,
    color: str = "#4a44c2",
    order_index: int | None = None,
    ai_proposed: bool = False,
) -> dict[str, Any]:
    if order_index is None:
        cur = conn.execute(
            "SELECT COALESCE(MAX(order_index), -1) + 1 AS next FROM themes WHERE project_id = ?",
            (project_id,),
        )
        order_index = int(cur.fetchone()["next"])
    theme_id = _new_id("t")
    conn.execute(
        """
        INSERT INTO themes (id, project_id, name, color, order_index, ai_proposed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (theme_id, project_id, name, color, order_index, 1 if ai_proposed else 0, _now_iso()),
    )
    fetched = get_theme(conn, theme_id)
    assert fetched is not None
    return fetched


def get_theme(conn: sqlite3.Connection, theme_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM themes WHERE id = ?", (theme_id,))
    return _row(cur.fetchone())


def list_themes(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM themes WHERE project_id = ? ORDER BY order_index ASC, created_at ASC",
        (project_id,),
    )
    return _rows(cur.fetchall())


def update_theme(
    conn: sqlite3.Connection,
    theme_id: str,
    *,
    name: str | None = None,
    color: str | None = None,
    order_index: int | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if color is not None:
        fields.append("color = ?")
        values.append(color)
    if order_index is not None:
        fields.append("order_index = ?")
        values.append(order_index)
    if not fields:
        return get_theme(conn, theme_id)
    values.append(theme_id)
    conn.execute(f"UPDATE themes SET {', '.join(fields)} WHERE id = ?", values)
    return get_theme(conn, theme_id)


def assign_stack_to_theme(
    conn: sqlite3.Connection,
    *,
    stack_id: str,
    theme_id: str,
    exclusive: bool = True,
) -> None:
    if exclusive:
        conn.execute("DELETE FROM stack_themes WHERE stack_id = ?", (stack_id,))
    conn.execute(
        "INSERT OR IGNORE INTO stack_themes (stack_id, theme_id) VALUES (?, ?)",
        (stack_id, theme_id),
    )


def list_stack_ids_for_theme(conn: sqlite3.Connection, theme_id: str) -> list[str]:
    cur = conn.execute(
        "SELECT stack_id FROM stack_themes WHERE theme_id = ?",
        (theme_id,),
    )
    return [row["stack_id"] for row in cur.fetchall()]


# ------------------------------------------------------------- pages/items --

def create_page(
    conn: sqlite3.Connection,
    *,
    theme_id: str,
    layout_id: str = "grid-2x2",
    order_index: int | None = None,
) -> dict[str, Any]:
    if order_index is None:
        cur = conn.execute(
            "SELECT COALESCE(MAX(order_index), -1) + 1 AS next FROM pages WHERE theme_id = ?",
            (theme_id,),
        )
        order_index = int(cur.fetchone()["next"])
    page_id = _new_id("pg")
    conn.execute(
        """
        INSERT INTO pages (id, theme_id, order_index, layout_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (page_id, theme_id, order_index, layout_id, _now_iso()),
    )
    fetched = get_page(conn, page_id)
    assert fetched is not None
    return fetched


def get_page(conn: sqlite3.Connection, page_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,))
    return _row(cur.fetchone())


def list_pages(conn: sqlite3.Connection, theme_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM pages WHERE theme_id = ? ORDER BY order_index ASC",
        (theme_id,),
    )
    return _rows(cur.fetchall())


def update_page(
    conn: sqlite3.Connection,
    page_id: str,
    *,
    layout_id: str | None = None,
    order_index: int | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if layout_id is not None:
        fields.append("layout_id = ?")
        values.append(layout_id)
    if order_index is not None:
        fields.append("order_index = ?")
        values.append(order_index)
    if not fields:
        return get_page(conn, page_id)
    values.append(page_id)
    conn.execute(f"UPDATE pages SET {', '.join(fields)} WHERE id = ?", values)
    return get_page(conn, page_id)


def add_page_item(
    conn: sqlite3.Connection,
    *,
    page_id: str,
    kind: str,
    slot_index: int,
    reference_id: str | None = None,
    text_content: str | None = None,
    position_json: str = "{}",
) -> dict[str, Any]:
    if kind not in {"photo", "text"}:
        raise ValueError(f"Unknown page item kind: {kind!r}")
    if kind == "photo" and reference_id is None:
        raise ValueError("Photo items require a reference_id.")
    if kind == "text" and text_content is None:
        raise ValueError("Text items require text_content.")

    item_id = _new_id("pi")
    conn.execute(
        """
        INSERT INTO page_items (
            id, page_id, kind, reference_id, text_content,
            slot_index, position_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, page_id, kind, reference_id, text_content, slot_index, position_json, _now_iso()),
    )
    fetched = get_page_item(conn, item_id)
    assert fetched is not None
    return fetched


def get_page_item(conn: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM page_items WHERE id = ?", (item_id,))
    return _row(cur.fetchone())


def list_page_items(conn: sqlite3.Connection, page_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM page_items WHERE page_id = ? ORDER BY slot_index ASC",
        (page_id,),
    )
    return _rows(cur.fetchall())


def update_page_item(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    reference_id: str | None = None,
    text_content: str | None = None,
    slot_index: int | None = None,
    position_json: str | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if reference_id is not None:
        fields.append("reference_id = ?")
        values.append(reference_id)
    if text_content is not None:
        fields.append("text_content = ?")
        values.append(text_content)
    if slot_index is not None:
        fields.append("slot_index = ?")
        values.append(slot_index)
    if position_json is not None:
        fields.append("position_json = ?")
        values.append(position_json)
    if not fields:
        return get_page_item(conn, item_id)
    values.append(item_id)
    conn.execute(f"UPDATE page_items SET {', '.join(fields)} WHERE id = ?", values)
    return get_page_item(conn, item_id)


def delete_page_item(conn: sqlite3.Connection, item_id: str) -> bool:
    cur = conn.execute("DELETE FROM page_items WHERE id = ?", (item_id,))
    return cur.rowcount > 0


# -------------------------------------------------------------------- jobs --

def create_job(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    kind: str,
) -> dict[str, Any]:
    job_id = _new_id("j")
    conn.execute(
        """
        INSERT INTO jobs (id, project_id, kind, status, progress, created_at)
        VALUES (?, ?, ?, 'queued', 0.0, ?)
        """,
        (job_id, project_id, kind, _now_iso()),
    )
    fetched = get_job(conn, job_id)
    assert fetched is not None
    return fetched


def get_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return _row(cur.fetchone())


def update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    error: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if progress is not None:
        fields.append("progress = ?")
        values.append(progress)
    if message is not None:
        fields.append("message = ?")
        values.append(message)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if started:
        fields.append("started_at = ?")
        values.append(_now_iso())
    if finished:
        fields.append("finished_at = ?")
        values.append(_now_iso())
    if not fields:
        return get_job(conn, job_id)
    values.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
    return get_job(conn, job_id)
