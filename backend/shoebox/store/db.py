"""SQLite connection helper.

One connection per request/job for simplicity. SQLite handles concurrent
reads fine in WAL mode; writes serialise naturally at the DB level,
which matches our last-write-wins concurrency policy.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from shoebox.config import get_settings
from shoebox.store.schema import SCHEMA_SQL


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialise(db_path: Path | None = None) -> None:
    """Create tables idempotently. Safe to call on every startup."""
    path = db_path or get_settings().db_path
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
    finally:
        conn.close()


@contextmanager
def connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context-managed connection. Always closes."""
    path = db_path or get_settings().db_path
    conn = _connect(path)
    try:
        yield conn
    finally:
        conn.close()
