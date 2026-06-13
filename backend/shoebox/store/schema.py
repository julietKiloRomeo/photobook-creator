"""SQLite schema for shoebox.

One DB per install (default ``data/shoebox.db``). Tables are namespaced
by ``project_id`` rather than per-project DBs to keep export and
multi-project listing cheap.

The schema lives here as one SQL string so it's reviewable as a single
artifact. Migrations are out of scope in M1; the schema is created idempotently
on startup. When we need to evolve it, we'll introduce a tiny
versioned-migrations module.

Members and votes tables are defined now (unused until M2/M3) so the
foreign keys on ``references_`` and ``stacks`` don't have to be added
later.

Why ``references_`` with the trailing underscore? ``references`` is a
SQL reserved word.
"""

from __future__ import annotations

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

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

CREATE INDEX IF NOT EXISTS idx_members_project ON members(project_id);

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

CREATE INDEX IF NOT EXISTS idx_references_project ON references_(project_id);
CREATE INDEX IF NOT EXISTS idx_references_captured ON references_(project_id, captured_at);

CREATE TABLE IF NOT EXISTS stacks (
    id                    TEXT PRIMARY KEY,
    project_id            TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    picked_reference_id   TEXT REFERENCES references_(id) ON DELETE SET NULL,
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stacks_project ON stacks(project_id);

CREATE TABLE IF NOT EXISTS stack_references (
    stack_id     TEXT NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
    reference_id TEXT NOT NULL REFERENCES references_(id) ON DELETE CASCADE,
    PRIMARY KEY (stack_id, reference_id)
);

CREATE INDEX IF NOT EXISTS idx_stack_refs_ref ON stack_references(reference_id);

CREATE TABLE IF NOT EXISTS votes (
    member_id    TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    stack_id     TEXT NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
    reference_id TEXT NOT NULL REFERENCES references_(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (member_id, stack_id)
);

CREATE TABLE IF NOT EXISTS themes (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    color        TEXT NOT NULL DEFAULT '#4a44c2',
    order_index  INTEGER NOT NULL DEFAULT 0,
    ai_proposed  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_themes_project ON themes(project_id, order_index);

CREATE TABLE IF NOT EXISTS stack_themes (
    stack_id  TEXT NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
    theme_id  TEXT NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    PRIMARY KEY (stack_id, theme_id)
);

CREATE INDEX IF NOT EXISTS idx_stack_themes_theme ON stack_themes(theme_id);

CREATE TABLE IF NOT EXISTS pages (
    id           TEXT PRIMARY KEY,
    theme_id     TEXT NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    order_index  INTEGER NOT NULL DEFAULT 0,
    layout_id    TEXT NOT NULL DEFAULT 'grid-2x2',
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pages_theme ON pages(theme_id, order_index);

CREATE TABLE IF NOT EXISTS page_items (
    id            TEXT PRIMARY KEY,
    page_id       TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    reference_id  TEXT REFERENCES references_(id) ON DELETE SET NULL,
    text_content  TEXT,
    slot_index    INTEGER NOT NULL DEFAULT 0,
    position_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_page_items_page ON page_items(page_id, slot_index);

CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',
    progress     REAL NOT NULL DEFAULT 0.0,
    message      TEXT,
    error        TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, created_at);
"""
