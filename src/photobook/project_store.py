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

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    total INTEGER NOT NULL,
    completed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
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
        groups = conn.execute(
            """
            SELECT id
            FROM duplicate_groups
            ORDER BY id
            """
        ).fetchall()
        photos = conn.execute(
            """
            SELECT group_id, photo_path, distance, is_best
            FROM duplicate_photos
            ORDER BY group_id, is_best DESC, distance ASC
            """
        ).fetchall()

    group_list = [dict(row) for row in groups]
    photos_by_group: dict[int, list[dict[str, object]]] = {}
    for row in photos:
        entry = dict(row)
        group_id = int(entry.pop("group_id"))
        photos_by_group.setdefault(group_id, []).append(entry)

    for group in group_list:
        group_id = group["id"]
        if group_id is None:
            raise ValueError("Duplicate group id missing")
        group_id = int(group_id)
        group["photos"] = photos_by_group.get(group_id, [])

    return group_list


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
