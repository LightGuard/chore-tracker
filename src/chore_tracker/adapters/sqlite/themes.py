"""SQLite persistence for theme preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chore_tracker.adapters.sqlite import transaction


class SQLiteThemePersistence:
    """Own SQL and transaction boundaries for theme preference writes."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def family_member_theme_status(
        self, family_member_id: int
    ) -> dict[str, Any] | None:
        with transaction(self._database_path) as connection:
            row = connection.execute(
                "SELECT id, is_active, theme_id FROM family_members WHERE id = ?",
                (family_member_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "is_active": bool(row["is_active"]),
            "theme_id": row["theme_id"],
        }

    def set_family_member_theme(self, family_member_id: int, theme_id: str) -> bool:
        with transaction(self._database_path) as connection:
            changed = connection.execute(
                """UPDATE family_members SET theme_id = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                   WHERE id = ?""",
                (theme_id, family_member_id),
            ).rowcount
        return changed == 1

    def set_administrator_theme(self, administrator_id: int, theme_id: str) -> bool:
        with transaction(self._database_path) as connection:
            changed = connection.execute(
                """UPDATE administrators SET theme_id = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                   WHERE id = ? AND is_active = 1""",
                (theme_id, administrator_id),
            ).rowcount
        return changed == 1
