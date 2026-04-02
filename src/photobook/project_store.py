from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_path TEXT NOT NULL,
    size INTEGER NOT NULL,
    path TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(photo_path, size)
);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_photos (
    cluster_id INTEGER NOT NULL,
    photo_path TEXT NOT NULL,
    rank INTEGER NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (cluster_id, photo_path)
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT
);

CREATE TABLE IF NOT EXISTS duplicate_photos (
    group_id INTEGER NOT NULL,
    photo_path TEXT NOT NULL,
    distance INTEGER NOT NULL,
    is_best INTEGER NOT NULL,
    PRIMARY KEY (group_id, photo_path)
);

CREATE TABLE IF NOT EXISTS ignored_duplicate_groups (
    group_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS ignored_photos (
    photo_path TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS resolved_duplicate_groups (
    group_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    total INTEGER NOT NULL,
    completed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS photo_scores (
    photo_path TEXT PRIMARY KEY,
    score REAL NOT NULL,
    model TEXT NOT NULL,
    device TEXT NOT NULL,
    computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    page_index INTEGER NOT NULL,
    UNIQUE(chapter_id, page_index)
);

CREATE TABLE IF NOT EXISTS page_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    photo_path TEXT,
    text TEXT,
    x REAL NOT NULL,
    y REAL NOT NULL,
    w REAL NOT NULL,
    h REAL NOT NULL,
    z INTEGER NOT NULL DEFAULT 0
);
"""


def ensure_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_SQL)


def upsert_thumbnail_records(db_path: Path, records: list[dict[str, str | int]]) -> int:
    if not records:
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executemany(
            """
            INSERT INTO thumbnails (photo_path, size, path, width, height)
            VALUES (:photo_path, :size, :path, :width, :height)
            ON CONFLICT(photo_path, size)
            DO UPDATE SET
                path = excluded.path,
                width = excluded.width,
                height = excluded.height
            """,
            records,
        )
        return conn.total_changes


def list_thumbnails(db_path: Path, limit: int = 2000) -> list[dict[str, str | int]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT photo_path, size, path, width, height, created_at
            FROM thumbnails
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_photo_paths(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT photo_path
            FROM thumbnails
            ORDER BY photo_path
            """,
        ).fetchall()
    return [row[0] for row in rows]


def list_thumbnail_paths(db_path: Path, size: int) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT photo_path, path
            FROM thumbnails
            WHERE size = ?
            """,
            (size,),
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def upsert_photo_scores(db_path: Path, records: list[dict[str, object]]) -> int:
    if not records:
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executemany(
            """
            INSERT INTO photo_scores (photo_path, score, model, device, computed_at)
            VALUES (:photo_path, :score, :model, :device, :computed_at)
            ON CONFLICT(photo_path)
            DO UPDATE SET
                score = excluded.score,
                model = excluded.model,
                device = excluded.device,
                computed_at = excluded.computed_at
            """,
            records,
        )
        return conn.total_changes


def list_photo_scores(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT photo_path, score, model, device, computed_at
            FROM photo_scores
            ORDER BY score DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_photo_scores_map(db_path: Path) -> dict[str, float]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT photo_path, score
            FROM photo_scores
            """
        ).fetchall()
    return {row[0]: float(row[1]) for row in rows}


def create_chapter(db_path: Path, name: str, page_count: int = 0) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(order_index), 0)
            FROM chapters
            """
        ).fetchone()
        order_index = int(row[0]) + 1 if row else 1
        cursor = conn.execute(
            """
            INSERT INTO chapters (name, order_index, page_count)
            VALUES (?, ?, ?)
            """,
            (name, order_index, page_count),
        )
        if cursor.lastrowid is None:
            raise ValueError("Expected chapter id from insert")
        chapter_id = int(cursor.lastrowid)
    if page_count:
        sync_pages_for_chapter(db_path, chapter_id, page_count)
    return chapter_id


def list_chapters(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, order_index, page_count, created_at
            FROM chapters
            ORDER BY order_index
            """
        ).fetchall()
    return [dict(row) for row in rows]


def update_chapter(db_path: Path, chapter_id: int, name: str | None = None) -> None:
    if name is None:
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE chapters
            SET name = ?
            WHERE id = ?
            """,
            (name, chapter_id),
        )


def reorder_chapters(db_path: Path, ordered_ids: list[int]) -> None:
    if not ordered_ids:
        return
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            UPDATE chapters
            SET order_index = ?
            WHERE id = ?
            """,
            [(index + 1, chapter_id) for index, chapter_id in enumerate(ordered_ids)],
        )


def sync_pages_for_chapter(db_path: Path, chapter_id: int, page_count: int) -> None:
    with sqlite3.connect(db_path) as conn:
        existing_rows = conn.execute(
            """
            SELECT id, page_index
            FROM pages
            WHERE chapter_id = ?
            ORDER BY page_index
            """,
            (chapter_id,),
        ).fetchall()
        existing_indexes = {row[1]: row[0] for row in existing_rows}
        to_create = [
            index for index in range(1, page_count + 1) if index not in existing_indexes
        ]
        to_delete = [row[0] for row in existing_rows if int(row[1]) > page_count]
        if to_delete:
            conn.executemany(
                """
                DELETE FROM page_items
                WHERE page_id = ?
                """,
                [(page_id,) for page_id in to_delete],
            )
            conn.executemany(
                """
                DELETE FROM pages
                WHERE id = ?
                """,
                [(page_id,) for page_id in to_delete],
            )
        if to_create:
            conn.executemany(
                """
                INSERT INTO pages (chapter_id, page_index)
                VALUES (?, ?)
                """,
                [(chapter_id, index) for index in to_create],
            )
        conn.execute(
            """
            UPDATE chapters
            SET page_count = ?
            WHERE id = ?
            """,
            (page_count, chapter_id),
        )


def list_pages(db_path: Path, chapter_id: int) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
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


def list_page_items(db_path: Path, page_id: int) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, page_id, item_type, photo_path, text, x, y, w, h, z
            FROM page_items
            WHERE page_id = ?
            ORDER BY z, id
            """,
            (page_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_page_item(
    db_path: Path,
    page_id: int,
    item_type: str,
    photo_path: str | None,
    text: str | None,
    x: float,
    y: float,
    w: float,
    h: float,
    z: int = 0,
) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO page_items (page_id, item_type, photo_path, text, x, y, w, h, z)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (page_id, item_type, photo_path, text, x, y, w, h, z),
        )
        if cursor.lastrowid is None:
            raise ValueError("Expected page item id from insert")
        return int(cursor.lastrowid)


def update_page_item(
    db_path: Path,
    item_id: int,
    x: float | None = None,
    y: float | None = None,
    w: float | None = None,
    h: float | None = None,
    z: int | None = None,
    text: str | None = None,
    photo_path: str | None = None,
) -> None:
    fields: list[str] = []
    values: list[object] = []
    if x is not None:
        fields.append("x = ?")
        values.append(x)
    if y is not None:
        fields.append("y = ?")
        values.append(y)
    if w is not None:
        fields.append("w = ?")
        values.append(w)
    if h is not None:
        fields.append("h = ?")
        values.append(h)
    if z is not None:
        fields.append("z = ?")
        values.append(z)
    if text is not None:
        fields.append("text = ?")
        values.append(text)
    if photo_path is not None:
        fields.append("photo_path = ?")
        values.append(photo_path)
    if not fields:
        return
    values.append(item_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE page_items
            SET {", ".join(fields)}
            WHERE id = ?
            """,
            values,
        )


def list_pages_with_items(db_path: Path, chapter_id: int) -> list[dict[str, object]]:
    pages = list_pages(db_path, chapter_id)
    if not pages:
        return []
    page_items: dict[int, list[dict[str, object]]] = {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, page_id, item_type, photo_path, text, x, y, w, h, z
            FROM page_items
            WHERE page_id IN ({placeholders})
            ORDER BY page_id, z, id
            """.format(placeholders=",".join("?" for _ in pages)),
            [page["id"] for page in pages],
        ).fetchall()
    for row in rows:
        entry = dict(row)
        page_id = int(entry.pop("page_id"))
        page_items.setdefault(page_id, []).append(entry)
    for page in pages:
        page_id = int(page["id"])
        page["items"] = page_items.get(page_id, [])
    return pages


def clear_clusters(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM cluster_photos")
        conn.execute("DELETE FROM clusters")


def create_cluster(
    db_path: Path, name: str, start_at: str, end_at: str, kind: str
) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO clusters (name, start_at, end_at, kind)
            VALUES (?, ?, ?, ?)
            """,
            (name, start_at, end_at, kind),
        )
        if cursor.lastrowid is None:
            raise ValueError("Expected cluster id from insert")
        return int(cursor.lastrowid)


def add_cluster_photos(
    db_path: Path, cluster_id: int, photos: list[dict[str, str | int]]
) -> None:
    if not photos:
        return
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO cluster_photos (cluster_id, photo_path, rank, role)
            VALUES (:cluster_id, :photo_path, :rank, :role)
            """,
            [
                {
                    "cluster_id": cluster_id,
                    "photo_path": photo["photo_path"],
                    "rank": photo["rank"],
                    "role": photo["role"],
                }
                for photo in photos
            ],
        )


def list_clusters(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        clusters = conn.execute(
            """
            SELECT id, name, start_at, end_at, kind
            FROM clusters
            ORDER BY start_at
            """
        ).fetchall()
        photos = conn.execute(
            """
            SELECT cluster_id, photo_path, rank, role
            FROM cluster_photos
            ORDER BY cluster_id, rank
            """
        ).fetchall()

    cluster_list = [dict(row) for row in clusters]
    photos_by_cluster: dict[int, list[dict[str, object]]] = {}
    for row in photos:
        entry = dict(row)
        cluster_id = int(entry.pop("cluster_id"))
        photos_by_cluster.setdefault(cluster_id, []).append(entry)

    for cluster in cluster_list:
        cluster_id = cluster["id"]
        if cluster_id is None:
            raise ValueError("Cluster id missing")
        cluster_id = int(cluster_id)
        cluster["photos"] = photos_by_cluster.get(cluster_id, [])

    return cluster_list


def clear_duplicate_groups(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM duplicate_photos")
        conn.execute("DELETE FROM duplicate_groups")


def create_duplicate_group(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("INSERT INTO duplicate_groups DEFAULT VALUES")
        if cursor.lastrowid is None:
            raise ValueError("Expected duplicate group id from insert")
        return int(cursor.lastrowid)


def add_duplicate_photos(
    db_path: Path, group_id: int, photos: list[dict[str, str | int]]
) -> None:
    if not photos:
        return
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO duplicate_photos (group_id, photo_path, distance, is_best)
            VALUES (:group_id, :photo_path, :distance, :is_best)
            """,
            [
                {
                    "group_id": group_id,
                    "photo_path": photo["photo_path"],
                    "distance": photo["distance"],
                    "is_best": photo["is_best"],
                }
                for photo in photos
            ],
        )


def list_duplicate_groups(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ignored_groups = {
            int(row[0])
            for row in conn.execute(
                """
                SELECT group_id
                FROM ignored_duplicate_groups
                """
            ).fetchall()
        }
        ignored_photos = {
            row[0]
            for row in conn.execute(
                """
                SELECT photo_path
                FROM ignored_photos
                """
            ).fetchall()
        }
        resolved_groups = {
            int(row[0])
            for row in conn.execute(
                """
                SELECT group_id
                FROM resolved_duplicate_groups
                """
            ).fetchall()
        }
        groups = conn.execute(
            """
            SELECT id
            FROM duplicate_groups
            ORDER BY id
            """
        ).fetchall()
        photos = conn.execute(
            """
            SELECT
                duplicate_photos.group_id,
                duplicate_photos.photo_path,
                duplicate_photos.distance,
                duplicate_photos.is_best,
                photo_scores.score,
                (
                    SELECT path
                    FROM thumbnails
                    WHERE thumbnails.photo_path = duplicate_photos.photo_path
                    ORDER BY size ASC
                    LIMIT 1
                ) AS thumb_path
            FROM duplicate_photos
            LEFT JOIN photo_scores
                ON duplicate_photos.photo_path = photo_scores.photo_path
            ORDER BY duplicate_photos.group_id, duplicate_photos.is_best DESC, duplicate_photos.distance ASC
            """
        ).fetchall()

    group_list = [dict(row) for row in groups]
    photos_by_group: dict[int, list[dict[str, object]]] = {}
    for row in photos:
        entry = dict(row)
        if entry.get("photo_path") in ignored_photos:
            continue
        group_id = int(entry.pop("group_id"))
        photos_by_group.setdefault(group_id, []).append(entry)

    for group in group_list:
        group_id = group["id"]
        if group_id is None:
            raise ValueError("Duplicate group id missing")
        group_id = int(group_id)
        if group_id in ignored_groups:
            group["photos"] = []
            continue
        group["resolved"] = group_id in resolved_groups
        group["photos"] = photos_by_group.get(group_id, [])

    return [group for group in group_list if len(group.get("photos", [])) > 1]


def ignore_duplicate_group(db_path: Path, group_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO ignored_duplicate_groups (group_id)
            VALUES (?)
            """,
            (group_id,),
        )


def ignore_photo(db_path: Path, photo_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO ignored_photos (photo_path)
            VALUES (?)
            """,
            (photo_path,),
        )


def set_duplicate_group_resolved(db_path: Path, group_id: int, resolved: bool) -> None:
    with sqlite3.connect(db_path) as conn:
        if resolved:
            conn.execute(
                """
                INSERT OR IGNORE INTO resolved_duplicate_groups (group_id)
                VALUES (?)
                """,
                (group_id,),
            )
        else:
            conn.execute(
                """
                DELETE FROM resolved_duplicate_groups
                WHERE group_id = ?
                """,
                (group_id,),
            )


def list_duplicate_photo_paths(db_path: Path, group_id: int) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT photo_path
            FROM duplicate_photos
            WHERE group_id = ?
            """,
            (group_id,),
        ).fetchall()
    return [row[0] for row in rows]


def delete_photo_assets(db_path: Path, photo_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        thumb_rows = conn.execute(
            """
            SELECT path
            FROM thumbnails
            WHERE photo_path = ?
            """,
            (photo_path,),
        ).fetchall()
        for (thumb_path,) in thumb_rows:
            try:
                Path(thumb_path).unlink(missing_ok=True)
            except OSError:
                pass

        try:
            Path(photo_path).unlink(missing_ok=True)
        except OSError:
            pass

        conn.execute(
            """
            DELETE FROM thumbnails
            WHERE photo_path = ?
            """,
            (photo_path,),
        )
        conn.execute(
            """
            DELETE FROM duplicate_photos
            WHERE photo_path = ?
            """,
            (photo_path,),
        )
        conn.execute(
            """
            DELETE FROM cluster_photos
            WHERE photo_path = ?
            """,
            (photo_path,),
        )
        conn.execute(
            """
            DELETE FROM photo_scores
            WHERE photo_path = ?
            """,
            (photo_path,),
        )
        conn.execute(
            """
            DELETE FROM page_items
            WHERE photo_path = ?
            """,
            (photo_path,),
        )
        conn.execute(
            """
            DELETE FROM ignored_photos
            WHERE photo_path = ?
            """,
            (photo_path,),
        )

        group_rows = conn.execute(
            """
            SELECT group_id, COUNT(*)
            FROM duplicate_photos
            GROUP BY group_id
            HAVING COUNT(*) <= 1
            """,
        ).fetchall()
        for group_id, _ in group_rows:
            conn.execute(
                """
                DELETE FROM duplicate_photos
                WHERE group_id = ?
                """,
                (group_id,),
            )
            conn.execute(
                """
                DELETE FROM duplicate_groups
                WHERE id = ?
                """,
                (group_id,),
            )


def create_job(db_path: Path, job_id: str, kind: str, total: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO jobs (id, kind, status, total, completed)
            VALUES (?, ?, 'queued', ?, 0)
            """,
            (job_id, kind, total),
        )


def update_job_status(db_path: Path, job_id: str, status: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, job_id),
        )


def update_job_progress(db_path: Path, job_id: str, completed: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            UPDATE jobs
            SET completed = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (completed, job_id),
        )


def get_job(db_path: Path, job_id: str) -> dict[str, str | int] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, kind, status, total, completed, created_at, updated_at
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
    return dict(row) if row else None
