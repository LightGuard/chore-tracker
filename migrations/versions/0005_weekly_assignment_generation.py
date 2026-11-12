"""Persist weekly assignment generation and the rotation anchor.

Revision ID: 0005_weekly_assignment_generation
Revises: 0004_administrator_passkeys
"""

from __future__ import annotations

from alembic import op

revision = "0005_weekly_assignment_generation"
down_revision = "0004_administrator_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE assignment_rotation_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            first_week_start TEXT NOT NULL UNIQUE,
            initialized_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (date(first_week_start) IS NOT NULL),
            CHECK (strftime('%w', first_week_start) = '1')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE weekly_assignment_generations (
            week_start TEXT PRIMARY KEY,
            week_end TEXT NOT NULL,
            rotation_anchor TEXT NOT NULL
                REFERENCES assignment_rotation_state(first_week_start)
                ON DELETE RESTRICT,
            generated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (date(week_start) IS NOT NULL),
            CHECK (strftime('%w', week_start) = '1'),
            CHECK (week_end = date(week_start, '+6 days')),
            CHECK (date(rotation_anchor) IS NOT NULL),
            CHECK (strftime('%w', rotation_anchor) = '1'),
            CHECK (week_start >= rotation_anchor)
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_assignment_rotation_state_immutable_update
        BEFORE UPDATE ON assignment_rotation_state
        BEGIN
            SELECT RAISE(ABORT, 'assignment rotation state is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_assignment_rotation_state_immutable_delete
        BEFORE DELETE ON assignment_rotation_state
        BEGIN
            SELECT RAISE(ABORT, 'assignment rotation state cannot be deleted');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_assignment_generations_immutable_update
        BEFORE UPDATE ON weekly_assignment_generations
        BEGIN
            SELECT RAISE(ABORT, 'weekly assignment generations are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_assignment_generations_immutable_delete
        BEFORE DELETE ON weekly_assignment_generations
        BEGIN
            SELECT RAISE(ABORT, 'weekly assignment generations cannot be deleted');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_weekly_assignment_generations_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_assignment_generations_immutable_update")
    op.execute("DROP TRIGGER trg_assignment_rotation_state_immutable_delete")
    op.execute("DROP TRIGGER trg_assignment_rotation_state_immutable_update")
    op.execute("DROP TABLE weekly_assignment_generations")
    op.execute("DROP TABLE assignment_rotation_state")
