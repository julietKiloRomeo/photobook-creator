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


def set_stack_clusters(db_path: Path, clusters: list[dict[str, Any]]) -> None:
    clear_stack_clusters(db_path)
    rows: list[tuple[str, int, str, int]] = []
    for index, cluster in enumerate(clusters):
        stack_id = str(cluster["stack_id"])
        label = str(cluster.get("label") or f"Stack {index + 1}")
        for reference_id in cluster.get("reference_ids", []):
            rows.append((stack_id, int(reference_id), label, index + 1))
    if not rows:
        return

    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO stack_clusters (stack_id, reference_id, label, order_index)
            VALUES (?, ?, ?, ?)
            """,
            rows,
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
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM stack_picks")
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


def _default_stack_color(reference_id: int) -> str:
    return FALLBACK_STACK_COLORS[(reference_id - 1) % len(FALLBACK_STACK_COLORS)]


def ensure_default_theme(db_path: Path) -> None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM themes").fetchone()
        count = int(row[0]) if row else 0
        if count > 0:
            return
        conn.execute(
            "INSERT INTO themes (title, color, order_index) VALUES (?, ?, 1)",
            ("Highlights", DEFAULT_THEME_COLORS[0]),
        )


def list_themes(db_path: Path) -> list[dict[str, Any]]:
    ensure_default_theme(db_path)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, color, order_index, created_at FROM themes ORDER BY order_index, id"
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


def create_theme(db_path: Path, title: str, color: str | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(order_index), 0) FROM themes").fetchone()
        next_order = int(row[0]) + 1 if row else 1
        color_choice = color or DEFAULT_THEME_COLORS[(next_order - 1) % len(DEFAULT_THEME_COLORS)]
        cursor = conn.execute(
            "INSERT INTO themes (title, color, order_index) VALUES (?, ?, ?)",
            (title, color_choice, next_order),
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
    for key in ["title", "color"]:
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


def list_stacks(db_path: Path) -> list[dict[str, Any]]:
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
                "resolved": picked_reference is not None,
                "date": first_date,
                "theme_id": theme_id,
                "theme_title": theme["title"] if theme else None,
                "theme_color": theme["color"] if theme else None,
            }
        )

    return items


def list_timeline_items(db_path: Path) -> list[dict[str, Any]]:
    items = list_stacks(db_path)
    items.sort(key=lambda item: str(item.get("date") or ""))
    return items


def clear_book(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM chapters")


def auto_build_book(db_path: Path) -> list[dict[str, Any]]:
    clear_book(db_path)

    themes = list_themes(db_path)
    stacks = list_stacks(db_path)
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
