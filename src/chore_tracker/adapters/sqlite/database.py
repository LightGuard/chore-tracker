"""SQLite connection and transaction helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled."""
    configured_path = str(database_path)
    if configured_path == ":memory:" or configured_path.startswith("file:"):
        path = configured_path
    else:
        resolved_path = Path(configured_path).expanduser().resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        path = str(resolved_path)

    connection = sqlite3.connect(
        path,
        timeout=5.0,
        uri=path.startswith("file:"),
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        connection.close()
        raise RuntimeError("SQLite foreign-key enforcement could not be enabled.")

    return connection


@contextmanager
def transaction(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Provide one connection and commit or roll back its transaction."""
    connection = connect(database_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
