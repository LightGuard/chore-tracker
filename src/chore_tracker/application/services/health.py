"""Application-level liveness and persistence readiness checks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.script import ScriptDirectory

from chore_tracker.adapters.sqlite import connect

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[4] / "migrations"


def get_health_status() -> dict[str, str]:
    """Return process liveness without depending on infrastructure."""
    return {"status": "ok"}


def is_database_ready(database_path: str | Path) -> bool:
    """Return whether SQLite is accessible and migrated to the current Alembic head.

    The check never creates a missing database file. Migration files are the source
    of truth for the expected schema revision, so adding a migration does not require
    a second manually maintained revision constant.
    """
    configured_path = str(database_path)
    if configured_path != ":memory:" and not configured_path.startswith("file:"):
        if not Path(configured_path).expanduser().is_file():
            return False

    connection: sqlite3.Connection | None = None
    try:
        expected_revision = ScriptDirectory(str(MIGRATIONS_DIRECTORY)).get_current_head()
        if expected_revision is None:
            return False

        connection = connect(database_path)
        row = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        return row is not None and row["version_num"] == expected_revision
    except Exception:
        # Readiness is deliberately fail-closed and never exposes infrastructure
        # details in its HTTP response.
        return False
    finally:
        if connection is not None:
            connection.close()
