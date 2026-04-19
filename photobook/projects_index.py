from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3
from pathlib import Path
import secrets
import shutil


DEFAULT_DATA_DIR = ".photobook-data"

INDEX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def get_data_root() -> Path:
    return Path(DEFAULT_DATA_DIR)


def get_index_db_path() -> Path:
    return get_data_root() / "index.db"


def get_projects_root() -> Path:
    return get_data_root() / "projects"


def get_project_root(project_id: str) -> Path:
    return get_projects_root() / project_id


def get_project_db_path(project_id: str) -> Path:
    return get_project_root(project_id) / "project.db"


def get_project_originals_dir(project_id: str) -> Path:
    return get_project_root(project_id) / "originals"


def get_project_derived_dir(project_id: str) -> Path:
    return get_project_root(project_id) / "derived"


def _connect_index() -> sqlite3.Connection:
    path = get_index_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_index_schema() -> None:
    with _connect_index() as conn:
        conn.executescript(INDEX_SCHEMA_SQL)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "book"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_projects() -> list[dict[str, str]]:
    ensure_index_schema()
    with _connect_index() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, slug, name, created_at FROM projects ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_project(project_id: str) -> dict[str, str] | None:
    ensure_index_schema()
    with _connect_index() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, slug, name, created_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def create_project(name: str) -> dict[str, str]:
    ensure_index_schema()
    base_slug = _slugify(name)
    project_id = secrets.token_hex(6)

    with _connect_index() as conn:
        # Ensure unique slug by suffixing only when needed.
        slug = base_slug
        counter = 1
        while True:
            exists = conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone()
            if not exists:
                break
            counter += 1
            slug = f"{base_slug}-{counter}"

        conn.execute(
            "INSERT INTO projects (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            (project_id, slug, name, _now_iso()),
        )

    root = get_project_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    get_project_originals_dir(project_id).mkdir(parents=True, exist_ok=True)
    get_project_derived_dir(project_id).mkdir(parents=True, exist_ok=True)

    project = get_project(project_id)
    if project is None:
        raise RuntimeError("Project creation failed")
    return project


def ensure_default_project() -> dict[str, str]:
    projects = list_projects()
    if projects:
        return projects[0]
    return create_project("My First Book")


def reset_project_storage(project_id: str) -> None:
    root = get_project_root(project_id)
    if root.exists():
        shutil.rmtree(root)
    get_project_originals_dir(project_id).mkdir(parents=True, exist_ok=True)
    get_project_derived_dir(project_id).mkdir(parents=True, exist_ok=True)
