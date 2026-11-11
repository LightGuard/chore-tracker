"""Create administrators, family members, chores, and checklist definitions.

Revision ID: 0001_core_entities
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001_core_entities"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE administrators (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE family_members (
            id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (length(trim(display_name)) > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE chores (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (length(trim(name)) > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE chore_checklist_items (
            id INTEGER PRIMARY KEY,
            chore_id INTEGER NOT NULL
                REFERENCES chores(id) ON DELETE RESTRICT,
            label TEXT NOT NULL,
            position INTEGER NOT NULL CHECK (position >= 0),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (length(trim(label)) > 0),
            UNIQUE (chore_id, position)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_chore_checklist_items_chore "
        "ON chore_checklist_items(chore_id, is_active, position)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_chore_checklist_items_chore")
    op.execute("DROP TABLE chore_checklist_items")
    op.execute("DROP TABLE chores")
    op.execute("DROP TABLE family_members")
    op.execute("DROP TABLE administrators")
