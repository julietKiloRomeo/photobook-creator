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
