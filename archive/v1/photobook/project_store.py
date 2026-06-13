from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS intake_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    label TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    page_index INTEGER NOT NULL,
    UNIQUE(chapter_id, page_index),
    FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS page_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    reference_id INTEGER,
    text TEXT,
    x REAL NOT NULL,
    y REAL NOT NULL,
    w REAL NOT NULL,
    h REAL NOT NULL,
    z INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE,
    FOREIGN KEY(reference_id) REFERENCES intake_references(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS stack_picks (
    stack_id TEXT PRIMARY KEY,
    reference_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(reference_id) REFERENCES intake_references(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS theme_stacks (
    theme_id INTEGER NOT NULL,
    stack_id TEXT NOT NULL,
    PRIMARY KEY(theme_id, stack_id),
    UNIQUE(stack_id),
    FOREIGN KEY(theme_id) REFERENCES themes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    original_path TEXT NOT NULL,
    derived_path TEXT,
    is_supported_image INTEGER NOT NULL DEFAULT 0,
    ignored_reason TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    group_id TEXT NOT NULL,
    reference_id INTEGER NOT NULL,
    distance INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(group_id, reference_id),
    FOREIGN KEY(reference_id) REFERENCES intake_references(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stack_clusters (
    stack_id TEXT NOT NULL,
    reference_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(stack_id, reference_id),
    FOREIGN KEY(reference_id) REFERENCES intake_references(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stack_split_overrides (
    reference_id INTEGER PRIMARY KEY,
    stack_id TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(reference_id) REFERENCES intake_references(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cluster_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL DEFAULT 'final',
    operation_id TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stack_review_state (
    stack_id TEXT PRIMARY KEY,
    previous_pick_reference_id INTEGER,
    new_reference_ids_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT NOT NULL DEFAULT 'new_additions',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(previous_pick_reference_id) REFERENCES intake_references(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS stack_visibility (
    stack_id TEXT PRIMARY KEY,
    ignored INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS upload_operations (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    percent INTEGER NOT NULL DEFAULT 0,
    files_total INTEGER NOT NULL DEFAULT 0,
    files_done INTEGER NOT NULL DEFAULT 0,
    stacks_visible INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS upload_operation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(operation_id) REFERENCES upload_operations(id) ON DELETE CASCADE
);
"""


FALLBACK_STACK_COLORS = [
    "#C4D4E8",
    "#E8C8A0",
    "#C8E0C0",
    "#D8EEF8",
    "#C8C0D8",
    "#D4B890",
    "#E0D4C8",
]

DEFAULT_THEME_COLORS = ["#7F77DD", "#1D9E75", "#D85A30", "#378ADD", "#BA7517", "#D4537E"]


@dataclass(frozen=True)
class StackReference:
    id: int
    source: str
    source_type: str
    label: str
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class StackModel:
    id: str
    key: str
    label: str
    references: list[StackReference]


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        cols = conn.execute("PRAGMA table_info(themes)").fetchall()
        col_names = {str(item[1]) for item in cols}
        if "description" not in col_names:
            conn.execute("ALTER TABLE themes ADD COLUMN description TEXT NOT NULL DEFAULT ''")


def upsert_references(db_path: Path, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not references:
        return []

    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO intake_references (source, source_type, label, metadata_json)
            VALUES (:source, :source_type, :label, :metadata_json)
            ON CONFLICT(source)
            DO UPDATE SET
                source_type = excluded.source_type,
                label = excluded.label,
                metadata_json = excluded.metadata_json
            """,
            [
                {
                    "source": str(item["source"]),
                    "source_type": str(item.get("source_type", "path")),
                    "label": item.get("label"),
                    "metadata_json": json.dumps(item.get("metadata") or {}, separators=(",", ":")),
                }
                for item in references
            ],
        )

    return list_references(db_path)


def list_references(db_path: Path) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, source, source_type, label, metadata_json, created_at
            FROM intake_references
            ORDER BY id
            """
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        items.append(item)
    return items


def get_reference(db_path: Path, reference_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, source, source_type, label, metadata_json, created_at
            FROM intake_references
            WHERE id = ?
            """,
            (reference_id,),
        ).fetchone()

    if row is None:
        return None

    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    return item


def create_upload(
    db_path: Path,
    *,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    sha256: str,
    original_path: str,
    derived_path: str | None,
    is_supported_image: bool,
    ignored_reason: str | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    payload = metadata or {}
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO uploads (
              filename, content_type, size_bytes, sha256, original_path, derived_path,
              is_supported_image, ignored_reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                content_type,
                size_bytes,
                sha256,
                original_path,
                derived_path,
                1 if is_supported_image else 0,
                ignored_reason,
                json.dumps(payload, separators=(",", ":")),
            ),
        )
    return int(cursor.lastrowid)


def list_uploads(db_path: Path) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              id,
              filename,
              content_type,
              size_bytes,
              sha256,
              original_path,
              derived_path,
              is_supported_image,
              ignored_reason,
              metadata_json,
              created_at
            FROM uploads
            ORDER BY id
            """
        ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["is_supported_image"] = bool(item["is_supported_image"])
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        output.append(item)
    return output


def clear_uploads(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM uploads")


def clear_duplicate_groups(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM duplicate_groups")


def set_duplicate_groups(
    db_path: Path,
    groups: list[dict[str, Any]],
) -> None:
    clear_duplicate_groups(db_path)
    rows: list[tuple[str, int, int]] = []
    for group in groups:
        group_id = str(group["group_id"])
        for member in group.get("members", []):
            rows.append(
                (
                    group_id,
                    int(member["reference_id"]),
                    int(member.get("distance", 0)),
                )
            )

    if not rows:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO duplicate_groups (group_id, reference_id, distance) VALUES (?, ?, ?)",
            rows,
        )


def list_duplicate_groups(db_path: Path) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT group_id, reference_id, distance
            FROM duplicate_groups
            ORDER BY group_id, distance, reference_id
            """
        ).fetchall()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        grouped.setdefault(str(item["group_id"]), []).append(
            {
                "reference_id": int(item["reference_id"]),
                "distance": int(item["distance"]),
            }
        )
    return [{"group_id": group_id, "members": members} for group_id, members in grouped.items()]


def clear_stack_clusters(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM stack_clusters")


def _stack_clusters_by_id(clusters: list[dict[str, Any]]) -> dict[str, set[int]]:
    by_id: dict[str, set[int]] = {}
    for cluster in clusters:
        stack_id = str(cluster.get("stack_id") or "")
        if not stack_id:
            continue
        by_id[stack_id] = {int(reference_id) for reference_id in cluster.get("reference_ids", [])}
    return by_id


def set_stack_clusters(db_path: Path, clusters: list[dict[str, Any]]) -> None:
    rows: list[tuple[str, int, str, int]] = []
    new_clusters = _stack_clusters_by_id(clusters)
    for index, cluster in enumerate(clusters):
        stack_id = str(cluster["stack_id"])
        label = str(cluster.get("label") or f"Stack {index + 1}")
        for reference_id in cluster.get("reference_ids", []):
            rows.append((stack_id, int(reference_id), label, index + 1))

    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        old_cluster_rows = conn.execute(
            """
            SELECT stack_id, reference_id
            FROM stack_clusters
            ORDER BY stack_id, reference_id
            """
        ).fetchall()
        old_pick_rows = conn.execute("SELECT stack_id, reference_id FROM stack_picks").fetchall()
        old_review_rows = conn.execute(
            """
            SELECT stack_id, previous_pick_reference_id, new_reference_ids_json, reason
            FROM stack_review_state
            ORDER BY stack_id
            """
        ).fetchall()
        old_visibility_rows = conn.execute(
            """
            SELECT stack_id, ignored
            FROM stack_visibility
            ORDER BY stack_id
            """
        ).fetchall()

        old_clusters: dict[str, set[int]] = {}
        for row in old_cluster_rows:
            old_clusters.setdefault(str(row["stack_id"]), set()).add(int(row["reference_id"]))
        old_picks = {str(row["stack_id"]): int(row["reference_id"]) for row in old_pick_rows}

        old_reviews: dict[str, dict[str, Any]] = {}
        for row in old_review_rows:
            payload = dict(row)
            old_reviews[str(payload["stack_id"])] = {
                "previous_pick_reference_id": (
                    int(payload["previous_pick_reference_id"])
                    if payload["previous_pick_reference_id"] is not None
                    else None
                ),
                "new_reference_ids": [int(item) for item in json.loads(payload["new_reference_ids_json"] or "[]")],
                "reason": str(payload["reason"] or "new_additions"),
            }
        old_visibility = {str(row["stack_id"]): bool(row["ignored"]) for row in old_visibility_rows}

        mapped_old_for_new: dict[str, str] = {}
        used_old: set[str] = set()
        for new_stack_id, new_refs in sorted(new_clusters.items()):
            best_old: str | None = None
            best_overlap = 0
            best_ratio = -1.0
            for old_stack_id, old_refs in old_clusters.items():
                if old_stack_id in used_old:
                    continue
                overlap = len(new_refs.intersection(old_refs))
                if overlap <= 0:
                    continue
                ratio = overlap / max(len(old_refs), 1)
                if overlap > best_overlap or (overlap == best_overlap and ratio > best_ratio):
                    best_old = old_stack_id
                    best_overlap = overlap
                    best_ratio = ratio
            if best_old is not None:
                mapped_old_for_new[new_stack_id] = best_old
                used_old.add(best_old)

        desired_picks: dict[str, int] = {}
        desired_reviews: dict[str, dict[str, Any]] = {}
        desired_ignored: set[str] = set()
        for new_stack_id, new_refs in new_clusters.items():
            source_stack_id = mapped_old_for_new.get(new_stack_id, new_stack_id)
            old_refs = old_clusters.get(source_stack_id, set())
            if old_visibility.get(source_stack_id, False):
                desired_ignored.add(new_stack_id)
            candidate_pick = old_picks.get(source_stack_id)
            if candidate_pick is not None and candidate_pick not in new_refs:
                candidate_pick = None

            gained_refs = sorted(new_refs.difference(old_refs))
            if candidate_pick is not None and gained_refs:
                desired_reviews[new_stack_id] = {
                    "previous_pick_reference_id": candidate_pick,
                    "new_reference_ids": gained_refs,
                    "reason": "new_additions",
                }
            elif candidate_pick is not None:
                desired_picks[new_stack_id] = candidate_pick

            inherited_review = old_reviews.get(source_stack_id)
            if inherited_review is not None:
                previous_pick = inherited_review.get("previous_pick_reference_id")
                if previous_pick is not None and int(previous_pick) not in new_refs:
                    previous_pick = None
                inherited_new_ids = {
                    int(reference_id)
                    for reference_id in inherited_review.get("new_reference_ids", [])
                    if int(reference_id) in new_refs
                }
                inherited_new_ids.update(gained_refs)
                if previous_pick is not None and inherited_new_ids:
                    desired_reviews[new_stack_id] = {
                        "previous_pick_reference_id": int(previous_pick),
                        "new_reference_ids": sorted(inherited_new_ids),
                        "reason": str(inherited_review.get("reason") or "new_additions"),
                    }
                    desired_picks.pop(new_stack_id, None)

        conn.execute("DELETE FROM stack_clusters")
        if rows:
            conn.executemany(
                """
                INSERT INTO stack_clusters (stack_id, reference_id, label, order_index)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

        conn.execute("DELETE FROM stack_picks")
        if desired_picks:
            conn.executemany(
                """
                INSERT INTO stack_picks (stack_id, reference_id, updated_at)
                VALUES (?, ?, datetime('now'))
                """,
                [(stack_id, reference_id) for stack_id, reference_id in sorted(desired_picks.items())],
            )

        conn.execute("DELETE FROM stack_review_state")
        if desired_reviews:
            conn.executemany(
                """
                INSERT INTO stack_review_state (
                  stack_id, previous_pick_reference_id, new_reference_ids_json, reason, updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                [
                    (
                        stack_id,
                        payload["previous_pick_reference_id"],
                        json.dumps(payload["new_reference_ids"], separators=(",", ":")),
                        payload["reason"],
                    )
                    for stack_id, payload in sorted(desired_reviews.items())
                ],
            )

        conn.execute("DELETE FROM stack_visibility")
        if desired_ignored:
            conn.executemany(
                """
                INSERT INTO stack_visibility (stack_id, ignored, updated_at)
                VALUES (?, 1, datetime('now'))
                """,
                [(stack_id,) for stack_id in sorted(desired_ignored)],
            )


def list_stack_clusters(db_path: Path) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT stack_id, reference_id, label, order_index
            FROM stack_clusters
            ORDER BY order_index, stack_id, reference_id
            """
        ).fetchall()

    clusters: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        stack_id = str(item["stack_id"])
        entry = clusters.setdefault(
            stack_id,
            {
                "stack_id": stack_id,
                "label": str(item["label"]),
                "order_index": int(item["order_index"]),
                "reference_ids": [],
            },
        )
        entry["reference_ids"].append(int(item["reference_id"]))

    ordered = sorted(clusters.values(), key=lambda cluster: (cluster["order_index"], cluster["stack_id"]))
    for cluster in ordered:
        cluster["reference_ids"] = sorted(cluster["reference_ids"])
    return ordered


def list_stack_review_state(db_path: Path) -> dict[str, dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT stack_id, previous_pick_reference_id, new_reference_ids_json, reason, updated_at
            FROM stack_review_state
            ORDER BY stack_id
            """
        ).fetchall()

    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = dict(row)
        output[str(payload["stack_id"])] = {
            "previous_pick_reference_id": (
                int(payload["previous_pick_reference_id"])
                if payload["previous_pick_reference_id"] is not None
                else None
            ),
            "new_reference_ids": [int(item) for item in json.loads(payload["new_reference_ids_json"] or "[]")],
            "reason": str(payload["reason"] or "new_additions"),
            "updated_at": str(payload["updated_at"]),
        }
    return output


def clear_stack_review_state(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM stack_review_state")


def stack_visibility_map(db_path: Path) -> dict[str, bool]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT stack_id, ignored FROM stack_visibility ORDER BY stack_id").fetchall()
    return {str(stack_id): bool(ignored) for stack_id, ignored in rows}


def set_stack_ignored(db_path: Path, stack_id: str, ignored: bool) -> bool:
    exists = False
    with _connect(db_path) as conn:
        exists = (
            conn.execute("SELECT 1 FROM stack_clusters WHERE stack_id = ? LIMIT 1", (stack_id,)).fetchone()
            is not None
        )
    if not exists:
        exists = any(str(stack.id) == str(stack_id) for stack in derive_stacks(db_path))
    if not exists:
        return False

    with _connect(db_path) as conn:
        if ignored:
            conn.execute(
                """
                INSERT INTO stack_visibility (stack_id, ignored, updated_at)
                VALUES (?, 1, datetime('now'))
                ON CONFLICT(stack_id) DO UPDATE SET
                  ignored = 1,
                  updated_at = datetime('now')
                """,
                (stack_id,),
            )
        else:
            conn.execute("DELETE FROM stack_visibility WHERE stack_id = ?", (stack_id,))
    return True


def set_cluster_state(db_path: Path, state: str, operation_id: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO cluster_state (id, state, operation_id, updated_at)
            VALUES (1, ?, ?, datetime('now'))
            ON CONFLICT(id)
            DO UPDATE SET
              state = excluded.state,
              operation_id = excluded.operation_id,
              updated_at = datetime('now')
            """,
            (state, operation_id),
        )


def get_cluster_state(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT state, operation_id, updated_at FROM cluster_state WHERE id = 1").fetchone()
    if row is None:
        return {"state": "final", "operation_id": None, "updated_at": datetime.now(timezone.utc).isoformat()}
    payload = dict(row)
    return {
        "state": str(payload["state"] or "final"),
        "operation_id": payload["operation_id"],
        "updated_at": str(payload["updated_at"]),
    }


def create_upload_operation(db_path: Path, operation_id: str, *, files_total: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO upload_operations (
              id, status, phase, message, percent, files_total, files_done, stacks_visible, error, created_at, updated_at
            )
            VALUES (?, 'running', 'uploading', 'Receiving files', 0, ?, 0, 0, NULL, datetime('now'), datetime('now'))
            """,
            (operation_id, int(files_total)),
        )
    return update_upload_operation(
        db_path,
        operation_id,
        status="running",
        phase="uploading",
        message="Receiving files",
        percent=0,
        files_total=int(files_total),
        files_done=0,
        stacks_visible=0,
        append_event=True,
    )


def update_upload_operation(
    db_path: Path,
    operation_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    message: str | None = None,
    percent: int | None = None,
    files_total: int | None = None,
    files_done: int | None = None,
    stacks_visible: int | None = None,
    error: str | None = None,
    append_event: bool = True,
) -> dict[str, Any]:
    updates: list[str] = []
    values: list[Any] = []
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if phase is not None:
        updates.append("phase = ?")
        values.append(phase)
    if message is not None:
        updates.append("message = ?")
        values.append(message)
    if percent is not None:
        updates.append("percent = ?")
        values.append(int(percent))
    if files_total is not None:
        updates.append("files_total = ?")
        values.append(int(files_total))
    if files_done is not None:
        updates.append("files_done = ?")
        values.append(int(files_done))
    if stacks_visible is not None:
        updates.append("stacks_visible = ?")
        values.append(int(stacks_visible))
    if error is not None:
        updates.append("error = ?")
        values.append(error)

    if updates:
        with _connect(db_path) as conn:
            conn.execute(
                f"UPDATE upload_operations SET {', '.join(updates)}, updated_at = datetime('now') WHERE id = ?",
                [*values, operation_id],
            )

    current = get_upload_operation(db_path, operation_id)
    if current is None:
        return {}

    if append_event:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO upload_operation_events (operation_id, event_type, payload_json)
                VALUES (?, 'status', ?)
                """,
                (
                    operation_id,
                    json.dumps(
                        {
                            "operation_id": current.get("id"),
                            "status": current.get("status"),
                            "phase": current.get("phase"),
                            "message": current.get("message"),
                            "percent": current.get("percent"),
                            "files_total": current.get("files_total"),
                            "files_done": current.get("files_done"),
                            "stacks_visible": current.get("stacks_visible"),
                            "error": current.get("error"),
                            "updated_at": current.get("updated_at"),
                        },
                        separators=(",", ":"),
                    ),
                ),
            )

    return current


def get_upload_operation(db_path: Path, operation_id: str) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, status, phase, message, percent, files_total, files_done, stacks_visible, error, created_at, updated_at
            FROM upload_operations
            WHERE id = ?
            """,
            (operation_id,),
        ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["percent"] = int(payload.get("percent") or 0)
    payload["files_total"] = int(payload.get("files_total") or 0)
    payload["files_done"] = int(payload.get("files_done") or 0)
    payload["stacks_visible"] = int(payload.get("stacks_visible") or 0)
    return payload


def get_latest_upload_operation(db_path: Path, *, active_only: bool = False) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if active_only:
            row = conn.execute(
                """
                SELECT id, status, phase, message, percent, files_total, files_done, stacks_visible, error, created_at, updated_at
                FROM upload_operations
                WHERE status = 'running'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, status, phase, message, percent, files_total, files_done, stacks_visible, error, created_at, updated_at
                FROM upload_operations
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()

    if row is None:
        return None
    payload = dict(row)
    payload["percent"] = int(payload.get("percent") or 0)
    payload["files_total"] = int(payload.get("files_total") or 0)
    payload["files_done"] = int(payload.get("files_done") or 0)
    payload["stacks_visible"] = int(payload.get("stacks_visible") or 0)
    return payload


def list_upload_operation_events(db_path: Path, operation_id: str, *, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, operation_id, event_type, payload_json, created_at
            FROM upload_operation_events
            WHERE operation_id = ? AND id > ?
            ORDER BY id
            LIMIT ?
            """,
            (operation_id, int(after_id), int(limit)),
        ).fetchall()

    events: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["data"] = json.loads(payload.pop("payload_json") or "{}")
        events.append(payload)
    return events


def mark_stale_upload_operations(db_path: Path, *, stale_seconds: int = 120) -> int:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM upload_operations
            WHERE status = 'running'
              AND updated_at < datetime('now', ?)
            ORDER BY updated_at
            """,
            (f"-{int(stale_seconds)} seconds",),
        ).fetchall()
    stale_ids = [str(row[0]) for row in rows]
    for operation_id in stale_ids:
        update_upload_operation(
            db_path,
            operation_id,
            status="failed",
            phase="failed",
            message="Upload worker interrupted",
            error="worker_interrupted",
            percent=100,
            append_event=True,
        )
    return len(stale_ids)


def clear_upload_operations(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM upload_operation_events")
        conn.execute("DELETE FROM upload_operations")


def list_stack_split_overrides(db_path: Path) -> dict[int, dict[str, str]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT reference_id, stack_id, label
            FROM stack_split_overrides
            ORDER BY reference_id
            """
        ).fetchall()

    overrides: dict[int, dict[str, str]] = {}
    for row in rows:
        item = dict(row)
        overrides[int(item["reference_id"])] = {
            "stack_id": str(item["stack_id"]),
            "label": str(item["label"] or ""),
        }
    return overrides


def _make_stack_id(reference_ids: list[int], *, salt: str = "") -> str:
    digest = hashlib.sha1(
        f"{','.join(str(ref_id) for ref_id in sorted(reference_ids))}|{salt}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    return f"s-{digest[:12]}"


def split_stack_cluster(
    db_path: Path,
    stack_id: str,
    reference_ids: list[int],
    *,
    label: str | None = None,
) -> dict[str, Any]:
    clusters = list_stack_clusters(db_path)
    target = next((cluster for cluster in clusters if cluster["stack_id"] == stack_id), None)
    if target is None:
        raise ValueError("stack_not_found")

    existing_refs = [int(item) for item in target["reference_ids"]]
    selected = sorted({int(item) for item in reference_ids if int(item) in existing_refs})
    if not selected:
        raise ValueError("no_valid_reference_ids")
    if len(selected) >= len(existing_refs):
        raise ValueError("cannot_split_all_references")

    next_label = (label or "Custom split").strip() or "Custom split"
    new_stack_id = _make_stack_id(selected)
    used_ids = {str(cluster["stack_id"]) for cluster in clusters}
    salt_counter = 1
    while new_stack_id in used_ids:
        new_stack_id = _make_stack_id(selected, salt=f"manual-{salt_counter}")
        salt_counter += 1

    remainder = [ref_id for ref_id in existing_refs if ref_id not in selected]
    new_order = int(target.get("order_index", 0) or 0) + 1

    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM stack_clusters WHERE stack_id = ? AND reference_id IN ({})".format(
                ",".join("?" for _ in selected)
            ),
            [stack_id, *selected],
        )

        conn.executemany(
            """
            INSERT INTO stack_clusters (stack_id, reference_id, label, order_index)
            VALUES (?, ?, ?, ?)
            """,
            [(new_stack_id, ref_id, next_label, new_order) for ref_id in selected],
        )

        conn.executemany(
            """
            INSERT INTO stack_split_overrides (reference_id, stack_id, label)
            VALUES (?, ?, ?)
            ON CONFLICT(reference_id) DO UPDATE SET
              stack_id = excluded.stack_id,
              label = excluded.label,
              created_at = datetime('now')
            """,
            [(ref_id, new_stack_id, next_label) for ref_id in selected],
        )

        picked_row = conn.execute(
            "SELECT reference_id FROM stack_picks WHERE stack_id = ?",
            (stack_id,),
        ).fetchone()
        if picked_row is not None and int(picked_row[0]) not in remainder:
            conn.execute("DELETE FROM stack_picks WHERE stack_id = ?", (stack_id,))

        theme_row = conn.execute(
            "SELECT theme_id FROM theme_stacks WHERE stack_id = ?",
            (stack_id,),
        ).fetchone()
        if theme_row is not None:
            conn.execute(
                "INSERT OR IGNORE INTO theme_stacks (theme_id, stack_id) VALUES (?, ?)",
                (int(theme_row[0]), new_stack_id),
            )

        visibility_row = conn.execute(
            "SELECT ignored FROM stack_visibility WHERE stack_id = ?",
            (stack_id,),
        ).fetchone()
        if visibility_row is not None and bool(visibility_row[0]):
            conn.execute(
                "INSERT OR IGNORE INTO stack_visibility (stack_id, ignored, updated_at) VALUES (?, 1, datetime('now'))",
                (new_stack_id,),
            )

    return {
        "old_stack_id": stack_id,
        "new_stack_id": new_stack_id,
        "moved_reference_ids": selected,
        "remaining_reference_ids": remainder,
        "label": next_label,
    }


def clear_processing_state(db_path: Path) -> None:
    clear_duplicate_groups(db_path)
    clear_stack_clusters(db_path)
    clear_stack_review_state(db_path)
    clear_upload_operations(db_path)
    set_cluster_state(db_path, "final", None)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM stack_picks")
        conn.execute("DELETE FROM stack_visibility")
        conn.execute("DELETE FROM theme_stacks")
        conn.execute("DELETE FROM themes")
        conn.execute("DELETE FROM page_items")
        conn.execute("DELETE FROM pages")
        conn.execute("DELETE FROM chapters")


def seed_demo_references_if_empty(db_path: Path, root_dir: Path) -> bool:
    if list_references(db_path):
        return False

    manifest_path = root_dir / "tests" / "fixtures" / "vacation-20" / "manifest.json"
    seed_items: list[dict[str, Any]] = []

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for index, item in enumerate(manifest.get("items", []), start=1):
            rel_path = item.get("path") if isinstance(item, dict) else None
            if isinstance(rel_path, str):
                source = str((root_dir / rel_path).resolve())
            else:
                source = f"/demo/vacation_{index:02d}.jpg"

            tags = item.get("tags") if isinstance(item, dict) else None
            tag_list = tags if isinstance(tags, list) else []
            shot_date = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index - 1)).date()

            seed_items.append(
                {
                    "source": source,
                    "source_type": "path",
                    "label": item.get("id", f"vac-{index:02d}") if isinstance(item, dict) else f"vac-{index:02d}",
                    "metadata": {
                        "tags": tag_list,
                        "prompt": item.get("prompt") if isinstance(item, dict) else None,
                        "seed": item.get("seed") if isinstance(item, dict) else None,
                        "date": shot_date.isoformat(),
                    },
                }
            )

    if not seed_items:
        base_tags = ["beach", "mountain", "city", "forest", "desert", "harbor"]
        for index in range(1, 13):
            tag = base_tags[(index - 1) % len(base_tags)]
            shot_date = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index - 1)).date()
            seed_items.append(
                {
                    "source": f"/demo/photo_{index:02d}.jpg",
                    "source_type": "path",
                    "label": f"demo-{index:02d}",
                    "metadata": {"tags": [tag], "date": shot_date.isoformat()},
                }
            )

    upsert_references(db_path, seed_items)
    return True


def create_chapter(db_path: Path, name: str, page_count: int = 0) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(order_index), 0) FROM chapters").fetchone()
        next_order = int(row[0]) + 1 if row else 1
        cursor = conn.execute(
            "INSERT INTO chapters (name, order_index) VALUES (?, ?)",
            (name, next_order),
        )
        chapter_id = int(cursor.lastrowid)

    if page_count > 0:
        sync_pages_for_chapter(db_path, chapter_id, page_count)
    return chapter_id


def list_chapters(db_path: Path) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              c.id,
              c.name,
              c.order_index,
              c.created_at,
              COUNT(p.id) AS page_count
            FROM chapters c
            LEFT JOIN pages p ON p.chapter_id = c.id
            GROUP BY c.id, c.name, c.order_index, c.created_at
            ORDER BY c.order_index
            """
        ).fetchall()
    return [dict(row) for row in rows]


def chapter_exists(db_path: Path, chapter_id: int) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    return row is not None


def page_exists(db_path: Path, page_id: int) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM pages WHERE id = ?", (page_id,)).fetchone()
    return row is not None


def reference_exists(db_path: Path, reference_id: int) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM intake_references WHERE id = ?", (reference_id,)).fetchone()
    return row is not None


def update_chapter_name(db_path: Path, chapter_id: int, name: str | None) -> None:
    if name is None:
        return
    with _connect(db_path) as conn:
        conn.execute("UPDATE chapters SET name = ? WHERE id = ?", (name, chapter_id))


def reorder_chapters(db_path: Path, chapter_ids: list[int]) -> None:
    if not chapter_ids:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            "UPDATE chapters SET order_index = ? WHERE id = ?",
            [(index + 1, chapter_id) for index, chapter_id in enumerate(chapter_ids)],
        )


def sync_pages_for_chapter(db_path: Path, chapter_id: int, page_count: int) -> None:
    target = max(0, page_count)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, page_index FROM pages WHERE chapter_id = ? ORDER BY page_index",
            (chapter_id,),
        ).fetchall()

        existing = len(rows)
        if target > existing:
            conn.executemany(
                "INSERT INTO pages (chapter_id, page_index) VALUES (?, ?)",
                [(chapter_id, idx) for idx in range(existing + 1, target + 1)],
            )
        elif target < existing:
            conn.execute(
                "DELETE FROM pages WHERE chapter_id = ? AND page_index > ?",
                (chapter_id, target),
            )


def list_pages(db_path: Path, chapter_id: int) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, chapter_id, page_index
            FROM pages
            WHERE chapter_id = ?
            ORDER BY page_index
            """,
            (chapter_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_page_item(db_path: Path, page_id: int, payload: dict[str, Any]) -> int:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO page_items (
              page_id, item_type, reference_id, text, x, y, w, h, z
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                payload["item_type"],
                payload.get("reference_id"),
                payload.get("text"),
                payload["x"],
                payload["y"],
                payload["w"],
                payload["h"],
                payload.get("z", 0),
            ),
        )
        return int(cursor.lastrowid)


def list_page_items(db_path: Path, page_id: int) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              i.id,
              i.page_id,
              i.item_type,
              i.reference_id,
              r.source AS reference_source,
              i.text,
              i.x,
              i.y,
              i.w,
              i.h,
              i.z
            FROM page_items i
            LEFT JOIN intake_references r ON r.id = i.reference_id
            WHERE i.page_id = ?
            ORDER BY i.z, i.id
            """,
            (page_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_page_item(db_path: Path, item_id: int, payload: dict[str, Any]) -> None:
    if not payload:
        return

    fields = []
    values: list[Any] = []
    for key in ["x", "y", "w", "h", "z", "text", "reference_id"]:
        if key in payload:
            fields.append(f"{key} = ?")
            values.append(payload[key])

    if not fields:
        return

    values.append(item_id)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE page_items SET {', '.join(fields)} WHERE id = ?", values)


def item_exists(db_path: Path, item_id: int) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM page_items WHERE id = ?", (item_id,)).fetchone()
    return row is not None


def list_pages_with_items(db_path: Path, chapter_ids: list[int] | None = None) -> list[dict[str, Any]]:
    chapters = list_chapters(db_path)
    if chapter_ids:
        allowed = set(chapter_ids)
        chapters = [chapter for chapter in chapters if chapter["id"] in allowed]

    output: list[dict[str, Any]] = []
    for chapter in chapters:
        pages = []
        for page in list_pages(db_path, int(chapter["id"])):
            page_copy = dict(page)
            page_copy["items"] = list_page_items(db_path, int(page["id"]))
            pages.append(page_copy)
        chapter_copy = dict(chapter)
        chapter_copy["pages"] = pages
        output.append(chapter_copy)
    return output


def _slug(value: str) -> str:
    out = []
    prev_dash = False
    for ch in value.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    slug = "".join(out).strip("-")
    return slug or "stack"


def _stack_key_from_metadata(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    tags = metadata.get("tags")
    if isinstance(tags, list) and tags and isinstance(tags[0], str) and tags[0].strip():
        return tags[0].strip()
    if isinstance(item.get("label"), str) and item["label"].strip():
        return item["label"].split()[0]
    return str(item["source"])


def _stack_label_from_key(key: str) -> str:
    return f"{key.replace('-', ' ').title()} shots"


def _to_stack_reference(item: dict[str, Any]) -> StackReference:
    return StackReference(
        id=int(item["id"]),
        source=str(item["source"]),
        source_type=str(item["source_type"]),
        label=str(item.get("label") or f"Photo {item['id']}"),
        metadata=dict(item.get("metadata") or {}),
        created_at=str(item["created_at"]),
    )


def derive_stacks(db_path: Path) -> list[StackModel]:
    references = [_to_stack_reference(item) for item in list_references(db_path)]
    grouped: dict[str, list[StackReference]] = {}
    labels: dict[str, str] = {}

    for ref in references:
        key_name = _stack_key_from_metadata(
            {
                "id": ref.id,
                "source": ref.source,
                "label": ref.label,
                "metadata": ref.metadata,
            }
        )
        slug = _slug(key_name)
        grouped.setdefault(slug, []).append(ref)
        labels.setdefault(slug, _stack_label_from_key(key_name))

    stacks: list[StackModel] = []
    for slug, items in grouped.items():
        items_sorted = sorted(items, key=lambda item: item.id)
        stacks.append(
            StackModel(
                id=f"s-{slug}",
                key=slug,
                label=labels.get(slug, _stack_label_from_key(slug)),
                references=items_sorted,
            )
        )

    stacks.sort(key=lambda stack: stack.id)
    return stacks


def _stack_pick_map(db_path: Path) -> dict[str, int]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT stack_id, reference_id FROM stack_picks").fetchall()
    return {str(stack_id): int(reference_id) for stack_id, reference_id in rows}


def pick_stack_reference(db_path: Path, stack_id: str, reference_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO stack_picks (stack_id, reference_id, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(stack_id)
            DO UPDATE SET
              reference_id = excluded.reference_id,
              updated_at = datetime('now')
            """,
            (stack_id, reference_id),
        )
        conn.execute("DELETE FROM stack_review_state WHERE stack_id = ?", (stack_id,))


def _default_stack_color(reference_id: int) -> str:
    return FALLBACK_STACK_COLORS[(reference_id - 1) % len(FALLBACK_STACK_COLORS)]


def ensure_default_theme(db_path: Path) -> None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM themes").fetchone()
        count = int(row[0]) if row else 0
        if count > 0:
            return
        conn.execute(
            "INSERT INTO themes (title, description, color, order_index) VALUES (?, ?, ?, 1)",
            ("Highlights", "", DEFAULT_THEME_COLORS[0]),
        )


def list_themes(db_path: Path) -> list[dict[str, Any]]:
    ensure_default_theme(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, description, color, order_index, created_at FROM themes ORDER BY order_index, id"
        ).fetchall()
        assignments = conn.execute("SELECT theme_id, stack_id FROM theme_stacks").fetchall()

    stack_ids_by_theme: dict[int, list[str]] = {}
    for theme_id, stack_id in assignments:
        stack_ids_by_theme.setdefault(int(theme_id), []).append(str(stack_id))

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["stack_ids"] = sorted(stack_ids_by_theme.get(int(item["id"]), []))
        items.append(item)
    return items


def create_theme(db_path: Path, title: str, color: str | None = None, description: str | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(order_index), 0) FROM themes").fetchone()
        next_order = int(row[0]) + 1 if row else 1
        color_choice = color or DEFAULT_THEME_COLORS[(next_order - 1) % len(DEFAULT_THEME_COLORS)]
        cursor = conn.execute(
            "INSERT INTO themes (title, description, color, order_index) VALUES (?, ?, ?, ?)",
            (title, (description or "").strip(), color_choice, next_order),
        )
        theme_id = int(cursor.lastrowid)

    theme = next((item for item in list_themes(db_path) if item["id"] == theme_id), None)
    if theme is None:
        raise RuntimeError("Created theme could not be loaded")
    return theme


def theme_exists(db_path: Path, theme_id: int) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM themes WHERE id = ?", (theme_id,)).fetchone()
    return row is not None


def delete_theme(db_path: Path, theme_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM themes WHERE id = ?", (theme_id,))


def update_theme(db_path: Path, theme_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    updates = []
    values: list[Any] = []
    for key in ["title", "description", "color"]:
        if key in payload and payload[key] is not None:
            updates.append(f"{key} = ?")
            values.append(payload[key])

    if updates:
        values.append(theme_id)
        with _connect(db_path) as conn:
            conn.execute(f"UPDATE themes SET {', '.join(updates)} WHERE id = ?", values)

    if "stack_ids" in payload and isinstance(payload["stack_ids"], list):
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM theme_stacks WHERE theme_id = ?", (theme_id,))
            for stack_id in payload["stack_ids"]:
                conn.execute("DELETE FROM theme_stacks WHERE stack_id = ?", (str(stack_id),))
                conn.execute(
                    "INSERT INTO theme_stacks (theme_id, stack_id) VALUES (?, ?)",
                    (theme_id, str(stack_id)),
                )

    theme = next((item for item in list_themes(db_path) if item["id"] == theme_id), None)
    if theme is None:
        raise RuntimeError("Updated theme could not be loaded")
    return theme


def assign_stack_theme(db_path: Path, stack_id: str, theme_id: int | None) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM theme_stacks WHERE stack_id = ?", (stack_id,))
        if theme_id is not None:
            conn.execute(
                "INSERT INTO theme_stacks (theme_id, stack_id) VALUES (?, ?)",
                (theme_id, stack_id),
            )


def replace_themes_from_clusters(db_path: Path, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM theme_stacks")
        conn.execute("DELETE FROM themes")

    created_theme_ids: list[int] = []
    for index, cluster in enumerate(clusters):
        title = str(cluster.get("title") or f"Theme {index + 1}")
        color = cluster.get("color")
        theme = create_theme(db_path, title, color if isinstance(color, str) else None)
        theme_id = int(theme["id"])
        created_theme_ids.append(theme_id)
        for stack_id in cluster.get("stack_ids", []):
            assign_stack_theme(db_path, str(stack_id), theme_id)

    if not created_theme_ids:
        # Keep at least one editable theme in UI.
        create_theme(db_path, "Highlights", DEFAULT_THEME_COLORS[0])
    return list_themes(db_path)


def stack_theme_map(db_path: Path) -> dict[str, int]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT stack_id, theme_id FROM theme_stacks").fetchall()
    return {str(stack_id): int(theme_id) for stack_id, theme_id in rows}


def list_stacks(db_path: Path, *, include_ignored: bool = True) -> list[dict[str, Any]]:
    configured_clusters = list_stack_clusters(db_path)
    if configured_clusters:
        references_by_id = {
            int(item["id"]): _to_stack_reference(item)
            for item in list_references(db_path)
        }
        stacks: list[StackModel] = []
        for cluster in configured_clusters:
            refs = [
                references_by_id[reference_id]
                for reference_id in cluster["reference_ids"]
                if reference_id in references_by_id
            ]
            if not refs:
                continue
            stacks.append(
                StackModel(
                    id=str(cluster["stack_id"]),
                    key=str(cluster["stack_id"]),
                    label=str(cluster["label"]),
                    references=sorted(refs, key=lambda ref: ref.id),
                )
            )
    else:
        stacks = derive_stacks(db_path)

    picks = _stack_pick_map(db_path)
    review_map = list_stack_review_state(db_path)
    visibility_map = stack_visibility_map(db_path)
    theme_map = stack_theme_map(db_path)
    themes = {item["id"]: item for item in list_themes(db_path)}

    items: list[dict[str, Any]] = []
    for idx, stack in enumerate(stacks):
        photo_items = []
        for ref in stack.references:
            photo_items.append(
                {
                    "id": ref.id,
                    "source": ref.source,
                    "source_type": ref.source_type,
                    "label": ref.label,
                    "metadata": ref.metadata,
                    "date": ref.metadata.get("date") or ref.created_at,
                    "color": ref.metadata.get("color") or _default_stack_color(ref.id + idx),
                }
            )

        picked_reference = picks.get(stack.id)
        if picked_reference is not None and all(ref.id != picked_reference for ref in stack.references):
            picked_reference = None
        if picked_reference is None and len(stack.references) == 1:
            picked_reference = stack.references[0].id

        review = review_map.get(stack.id)
        review_previous_pick = None
        review_new_ids: list[int] = []
        if review is not None:
            candidate_prev = review.get("previous_pick_reference_id")
            if isinstance(candidate_prev, int) and any(ref.id == candidate_prev for ref in stack.references):
                review_previous_pick = candidate_prev
            review_new_ids = [
                int(ref_id)
                for ref_id in review.get("new_reference_ids", [])
                if any(ref.id == int(ref_id) for ref in stack.references)
            ]
        needs_review = bool(review_previous_pick is not None and review_new_ids)
        ignored = bool(visibility_map.get(stack.id, False))
        if ignored and not include_ignored:
            continue

        theme_id = theme_map.get(stack.id)
        theme = themes.get(theme_id) if theme_id is not None else None
        first_date = photo_items[0]["date"] if photo_items else None

        items.append(
            {
                "id": stack.id,
                "label": stack.label,
                "photo_ids": [ref.id for ref in stack.references],
                "photos": photo_items,
                "pick_reference_id": picked_reference,
                "resolved": picked_reference is not None and not needs_review,
                "needs_review": needs_review,
                "ignored": ignored,
                "previous_pick_reference_id": review_previous_pick,
                "new_reference_ids": review_new_ids,
                "date": first_date,
                "theme_id": theme_id,
                "theme_title": theme["title"] if theme else None,
                "theme_color": theme["color"] if theme else None,
            }
        )

    return items


def list_timeline_items(db_path: Path, *, include_ignored: bool = True) -> list[dict[str, Any]]:
    items = list_stacks(db_path, include_ignored=include_ignored)
    items.sort(key=lambda item: str(item.get("date") or ""))
    return items


def clear_book(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM chapters")


def auto_build_book(db_path: Path) -> list[dict[str, Any]]:
    clear_book(db_path)

    themes = list_themes(db_path)
    stacks = list_stacks(db_path, include_ignored=False)
    stacks_by_theme: dict[int, list[dict[str, Any]]] = {}
    for stack in stacks:
        theme_id = stack.get("theme_id")
        if theme_id is None:
            continue
        stacks_by_theme.setdefault(int(theme_id), []).append(stack)

    def _populate_chapter(chapter_title: str, chapter_stacks: list[dict[str, Any]]) -> None:
        if not chapter_stacks:
            return
        chapter_id = create_chapter(db_path, chapter_title, page_count=len(chapter_stacks))
        pages = list_pages(db_path, chapter_id)
        for page, stack in zip(pages, chapter_stacks):
            reference_id = stack.get("pick_reference_id")
            if reference_id is None:
                photo_ids = stack.get("photo_ids") or []
                reference_id = photo_ids[0] if photo_ids else None
            if reference_id is None:
                continue
            create_page_item(
                db_path,
                int(page["id"]),
                {
                    "item_type": "photo",
                    "reference_id": int(reference_id),
                    "x": 0.05,
                    "y": 0.05,
                    "w": 0.9,
                    "h": 0.9,
                    "z": 0,
                },
            )

    for theme in themes:
        themed_stacks = stacks_by_theme.get(int(theme["id"]), [])
        _populate_chapter(str(theme["title"]), themed_stacks)

    unassigned = [stack for stack in stacks if stack.get("theme_id") is None]
    _populate_chapter("Ungrouped", unassigned)

    return list_pages_with_items(db_path)


def delete_stack_with_references(db_path: Path, stack_id: str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ref_rows = conn.execute(
            """
            SELECT reference_id
            FROM stack_clusters
            WHERE stack_id = ?
            ORDER BY reference_id
            """,
            (stack_id,),
        ).fetchall()
        if not ref_rows:
            raise ValueError("stack_not_found")
        reference_ids = [int(row["reference_id"]) for row in ref_rows]
        placeholders = ",".join("?" for _ in reference_ids)

        reference_sources = conn.execute(
            f"""
            SELECT id, source
            FROM intake_references
            WHERE id IN ({placeholders})
            ORDER BY id
            """,
            reference_ids,
        ).fetchall()
        derived_paths = [str(row["source"]) for row in reference_sources if row["source"]]

        upload_rows: list[sqlite3.Row] = []
        if derived_paths:
            upload_placeholders = ",".join("?" for _ in derived_paths)
            upload_rows = conn.execute(
                f"""
                SELECT id, original_path, derived_path
                FROM uploads
                WHERE derived_path IN ({upload_placeholders})
                ORDER BY id
                """,
                derived_paths,
            ).fetchall()

        upload_ids = [int(row["id"]) for row in upload_rows]
        original_paths = [str(row["original_path"]) for row in upload_rows if row["original_path"]]

        conn.execute("DELETE FROM theme_stacks WHERE stack_id = ?", (stack_id,))
        conn.execute("DELETE FROM stack_review_state WHERE stack_id = ?", (stack_id,))
        conn.execute("DELETE FROM stack_picks WHERE stack_id = ?", (stack_id,))
        conn.execute("DELETE FROM stack_visibility WHERE stack_id = ?", (stack_id,))
        conn.execute("DELETE FROM stack_clusters WHERE stack_id = ?", (stack_id,))
        conn.execute(f"DELETE FROM page_items WHERE reference_id IN ({placeholders})", reference_ids)
        conn.execute(f"DELETE FROM stack_split_overrides WHERE reference_id IN ({placeholders})", reference_ids)
        conn.execute(f"DELETE FROM intake_references WHERE id IN ({placeholders})", reference_ids)
        if upload_ids:
            upload_id_placeholders = ",".join("?" for _ in upload_ids)
            conn.execute(f"DELETE FROM uploads WHERE id IN ({upload_id_placeholders})", upload_ids)

    return {
        "stack_id": stack_id,
        "reference_ids": reference_ids,
        "derived_paths": sorted({path for path in derived_paths if path}),
        "original_paths": sorted({path for path in original_paths if path}),
    }
