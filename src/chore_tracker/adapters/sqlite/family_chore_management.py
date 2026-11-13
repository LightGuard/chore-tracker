"""SQLite persistence adapter for family-member and chore management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chore_tracker.adapters.sqlite import transaction


class SQLiteFamilyChoreManagementPersistence:
    """Own SQL, row mapping, and transaction boundaries for management use cases."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    @staticmethod
    def _family_member(connection, family_member_id: int):
        row = connection.execute(
            """SELECT id, display_name, is_active, created_at, updated_at
               FROM family_members WHERE id = ?""",
            (family_member_id,),
        ).fetchone()
        return (
            {**dict(row), "is_active": bool(row["is_active"])}
            if row is not None
            else None
        )

    @staticmethod
    def _chore(connection, chore_id: int):
        row = connection.execute(
            """SELECT id, name, description, is_active, created_at, updated_at
               FROM chores WHERE id = ?""",
            (chore_id,),
        ).fetchone()
        return row

    @staticmethod
    def _item(connection, chore_id: int, item_id: int):
        return connection.execute(
            """SELECT id, chore_id, label, position, is_active, created_at, updated_at
               FROM chore_checklist_items WHERE id = ? AND chore_id = ?""",
            (item_id, chore_id),
        ).fetchone()

    @staticmethod
    def _active_item_count(connection, chore_id: int) -> int:
        return connection.execute(
            """SELECT COUNT(*) FROM chore_checklist_items
               WHERE chore_id = ? AND is_active = 1""",
            (chore_id,),
        ).fetchone()[0]

    @classmethod
    def _serialize_chore(cls, connection, chore_id: int):
        chore = cls._chore(connection, chore_id)
        if chore is None:
            return None
        items = connection.execute(
            """SELECT id, label, position, is_active, created_at, updated_at
               FROM chore_checklist_items WHERE chore_id = ?
               ORDER BY position, id""",
            (chore_id,),
        ).fetchall()
        return {
            **dict(chore),
            "is_active": bool(chore["is_active"]),
            "checklist_items": [
                {**dict(item), "is_active": bool(item["is_active"])} for item in items
            ],
        }

    def list_family_members(self) -> list[dict[str, Any]]:
        with transaction(self._database_path) as connection:
            rows = connection.execute(
                """SELECT id, display_name, is_active, created_at, updated_at
                   FROM family_members
                   ORDER BY display_name COLLATE NOCASE, id"""
            ).fetchall()
            return [{**dict(row), "is_active": bool(row["is_active"])} for row in rows]

    def create_family_member(self, display_name: str, is_active: bool):
        with transaction(self._database_path) as connection:
            member_id = connection.execute(
                """INSERT INTO family_members (display_name, is_active)
                   VALUES (?, ?)""",
                (display_name, int(is_active)),
            ).lastrowid
            return self._family_member(connection, member_id)

    def get_family_member(self, family_member_id: int):
        with transaction(self._database_path) as connection:
            return self._family_member(connection, family_member_id)

    def update_family_member(self, family_member_id: int, changes: dict[str, Any]):
        with transaction(self._database_path) as connection:
            if self._family_member(connection, family_member_id) is None:
                return None
            assignments = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(
                f"""UPDATE family_members SET {assignments},
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?""",
                (*changes.values(), family_member_id),
            )
            return self._family_member(connection, family_member_id)

    def list_chores(self) -> list[dict[str, Any]]:
        with transaction(self._database_path) as connection:
            ids = connection.execute(
                """SELECT id FROM chores
                   ORDER BY name COLLATE NOCASE, id"""
            ).fetchall()
            return [
                self._serialize_chore(connection, row["id"]) for row in ids
            ]

    def create_chore(self, name: str, description: str):
        with transaction(self._database_path) as connection:
            chore_id = connection.execute(
                """INSERT INTO chores (name, description, is_active)
                   VALUES (?, ?, 0)""",
                (name, description),
            ).lastrowid
            return self._serialize_chore(connection, chore_id)

    def get_chore(self, chore_id: int):
        with transaction(self._database_path) as connection:
            return self._serialize_chore(connection, chore_id)

    def update_chore(self, chore_id: int, changes: dict[str, Any]):
        with transaction(self._database_path) as connection:
            if self._chore(connection, chore_id) is None:
                return None
            if (
                changes.get("is_active") is True
                and self._active_item_count(connection, chore_id) == 0
            ):
                return {"conflict": "active_checklist_required"}
            assignments = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(
                f"""UPDATE chores SET {assignments},
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?""",
                (*changes.values(), chore_id),
            )
            return self._serialize_chore(connection, chore_id)

    def add_checklist_item(self, chore_id: int, label: str):
        with transaction(self._database_path) as connection:
            if self._chore(connection, chore_id) is None:
                return None
            position = connection.execute(
                """SELECT COALESCE(MAX(position), -1) + 1
                   FROM chore_checklist_items WHERE chore_id = ?""",
                (chore_id,),
            ).fetchone()[0]
            item_id = connection.execute(
                """INSERT INTO chore_checklist_items (chore_id, label, position)
                   VALUES (?, ?, ?)""",
                (chore_id, label, position),
            ).lastrowid
            item = self._item(connection, chore_id, item_id)
            return {**dict(item), "is_active": bool(item["is_active"])}

    def update_checklist_item(
        self, chore_id: int, item_id: int, changes: dict[str, Any]
    ):
        with transaction(self._database_path) as connection:
            chore = self._chore(connection, chore_id)
            current = self._item(connection, chore_id, item_id)
            if chore is None or current is None:
                return None
            if (
                chore["is_active"]
                and current["is_active"]
                and changes.get("is_active") is False
                and self._active_item_count(connection, chore_id) <= 1
            ):
                return {"conflict": "last_active_item"}
            assignments = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(
                f"""UPDATE chore_checklist_items SET {assignments},
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?""",
                (*changes.values(), item_id),
            )
            item = self._item(connection, chore_id, item_id)
            return {**dict(item), "is_active": bool(item["is_active"])}

    def delete_checklist_item(self, chore_id: int, item_id: int) -> str | None:
        with transaction(self._database_path) as connection:
            chore = self._chore(connection, chore_id)
            item = self._item(connection, chore_id, item_id)
            if chore is None:
                return "chore_missing"
            if item is None:
                return "item_missing"
            if (
                chore["is_active"]
                and item["is_active"]
                and self._active_item_count(connection, chore_id) <= 1
            ):
                return "last_active_item"
            connection.execute(
                "DELETE FROM chore_checklist_items WHERE id = ?", (item_id,)
            )
            return None

    def reorder_checklist(self, chore_id: int, ordered_item_ids: list[int]):
        with transaction(self._database_path) as connection:
            if self._chore(connection, chore_id) is None:
                return None
            existing = [
                row["id"]
                for row in connection.execute(
                    """SELECT id FROM chore_checklist_items
                       WHERE chore_id = ? ORDER BY position""",
                    (chore_id,),
                ).fetchall()
            ]
            if set(existing) != set(ordered_item_ids) or len(existing) != len(
                ordered_item_ids
            ):
                return {"invalid_order": True}
            offset = max(existing, default=-1) + len(existing) + 1
            connection.execute(
                """UPDATE chore_checklist_items SET position = position + ?
                   WHERE chore_id = ?""",
                (offset, chore_id),
            )
            for position, item_id in enumerate(ordered_item_ids):
                connection.execute(
                    """UPDATE chore_checklist_items SET position = ?,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                       WHERE id = ?""",
                    (position, item_id),
                )
            return self._serialize_chore(connection, chore_id)
