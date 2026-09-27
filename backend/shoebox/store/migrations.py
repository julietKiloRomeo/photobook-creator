"""Additive column migrations, applied on every startup.

``SCHEMA_SQL`` is idempotent for whole tables — ``CREATE TABLE IF NOT
EXISTS`` adds a new table to an existing database and leaves everything
else alone. It is *not* idempotent for a column added to a table that
already exists: that table is simply skipped, so a live database never
grows the new column.

This module closes that gap for the only kind of change shoebox makes:
adding a nullable column. Each migration names the column it introduces
and is skipped only when ``PRAGMA table_info`` proves the column is
already there. Nothing is dropped, nothing is rebuilt, and no exception
is swallowed — a genuine ``ALTER TABLE`` failure aborts startup.

Why a column probe rather than a ``user_version`` counter: a fresh
database and jkr's live one both start at version 0, yet only one of
them needs the ``ALTER``. Asking the database what it actually has is
the smaller and more honest question.

SQLite allows ``ADD COLUMN`` with a ``REFERENCES`` clause as long as the
column's default is NULL, which is exactly the shape of every migration
here.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import NamedTuple

log = logging.getLogger(__name__)


class AddColumn(NamedTuple):
    table: str
    column: str
    definition: str

    @property
    def statement(self) -> str:
        return f"ALTER TABLE {self.table} ADD COLUMN {self.column} {self.definition}"


MIGRATIONS: tuple[AddColumn, ...] = (
    AddColumn(
        table="references_",
        column="source_id",
        definition="TEXT REFERENCES sources(id) ON DELETE SET NULL",
    ),
)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to ``SCHEMA_SQL``. Safe to repeat."""
    for migration in MIGRATIONS:
        if migration.column in _columns(conn, migration.table):
            continue
        log.info("Adding column %s.%s", migration.table, migration.column)
        conn.execute(migration.statement)
