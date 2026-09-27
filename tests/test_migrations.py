"""The upgrade path for databases that predate a schema change.

``SCHEMA_SQL`` is applied with ``CREATE TABLE IF NOT EXISTS``, which
creates *new* tables on an existing database but never touches a table
that is already there. A column added to ``references_`` therefore only
appears on a brand-new database unless something explicitly adds it.

jkr runs shoebox against a live database holding real photos, so the
test that matters is the one below: build a database with the schema as
it shipped, put real rows in it, run ``initialise()``, and assert the
rows survived.
"""

from __future__ import annotations

import sqlite3

from shoebox.config import Settings
from shoebox.store import connection, initialise

# The schema exactly as it shipped before upload-batch provenance: no
# ``sources`` table, no ``references_.source_id``. Copied rather than
# imported so evolving ``SCHEMA_SQL`` cannot quietly weaken this test.
PRE_MIGRATION_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS members (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    color         TEXT NOT NULL,
    role          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS references_ (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    original_path   TEXT NOT NULL,
    file_hash       TEXT NOT NULL,
    phash           TEXT,
    captured_at     TEXT,
    gps_lat         REAL,
    gps_lon         REAL,
    width           INTEGER,
    height          INTEGER,
    uploader_member_id TEXT REFERENCES members(id) ON DELETE SET NULL,
    uploaded_at     TEXT NOT NULL,
    UNIQUE(project_id, file_hash)
);
"""

LEGACY_REFERENCE = {
    "id": "r_legacy",
    "project_id": "p_legacy",
    "original_path": "/data/projects/p_legacy/originals/deadbeef.jpg",
    "file_hash": "deadbeef",
    "phash": "ffff0000ffff0000",
    "captured_at": "2024-07-14T11:30:00+00:00",
    "gps_lat": 55.6761,
    "gps_lon": 12.5683,
    "width": 4032,
    "height": 3024,
    "uploader_member_id": None,
    "uploaded_at": "2024-07-15T09:00:00+00:00",
}


def _build_pre_migration_database(settings: Settings) -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, isolation_level=None)
    try:
        conn.executescript(PRE_MIGRATION_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO projects (id, name, created_at, status)"
            " VALUES ('p_legacy', 'Summer 2024', '2024-07-01T08:00:00+00:00', 'active')"
        )
        columns = ", ".join(LEGACY_REFERENCE)
        placeholders = ", ".join(["?"] * len(LEGACY_REFERENCE))
        conn.execute(
            f"INSERT INTO references_ ({columns}) VALUES ({placeholders})",
            tuple(LEGACY_REFERENCE.values()),
        )
    finally:
        conn.close()


def test_startup_upgrades_a_pre_migration_database_without_losing_photos(
    settings: Settings,
) -> None:
    _build_pre_migration_database(settings)

    initialise()

    with connection() as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "sources" in tables

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(references_)")}
        assert "source_id" in columns

        rows = conn.execute("SELECT * FROM references_").fetchall()
        assert len(rows) == 1
        survivor = dict(rows[0])
        assert survivor.pop("source_id") is None
        assert survivor == LEGACY_REFERENCE


def test_startup_is_repeatable_on_an_already_upgraded_database(
    settings: Settings,
) -> None:
    _build_pre_migration_database(settings)

    initialise()
    initialise()
    initialise()

    with connection() as conn:
        source_id_columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(references_)")
            if row["name"] == "source_id"
        ]
        assert source_id_columns == ["source_id"]
        assert conn.execute("SELECT COUNT(*) AS n FROM references_").fetchone()["n"] == 1
