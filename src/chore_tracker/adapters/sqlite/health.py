"""SQLite-backed database readiness probe."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.script import ScriptDirectory

from chore_tracker.adapters.sqlite import connect

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[3] / "migrations"


class SQLiteReadinessProbe:
    """Check SQLite accessibility and migration currency without creating a DB."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def is_ready(self) -> bool:
        configured_path = str(self._database_path)
        if configured_path != ":memory:" and not configured_path.startswith("file:"):
            if not Path(configured_path).expanduser().is_file():
                return False

        connection: sqlite3.Connection | None = None
        try:
            expected_revision = ScriptDirectory(
                str(MIGRATIONS_DIRECTORY)
            ).get_current_head()
            if expected_revision is None:
                return False

            connection = connect(self._database_path)
            row = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            return row is not None and row["version_num"] == expected_revision
        except Exception:
            # Readiness is fail-closed and does not expose infrastructure details.
            return False
        finally:
            if connection is not None:
                connection.close()
