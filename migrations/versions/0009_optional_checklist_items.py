"""Add required/optional flags to chore checklist items and assignment snapshots.

Revision ID: 0009_optional_checklist_items
Revises: 0008_theme_preferences
"""

from __future__ import annotations

from alembic import op

revision = "0009_optional_checklist_items"
down_revision = "0008_theme_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing items and snapshots keep the current completion behavior until an
    # administrator explicitly marks them optional.
    op.execute(
        "ALTER TABLE chore_checklist_items "
        "ADD COLUMN is_required INTEGER NOT NULL DEFAULT 1 "
        "CHECK (is_required IN (0, 1))"
    )
    op.execute(
        "ALTER TABLE assignment_checklist_items "
        "ADD COLUMN is_required INTEGER NOT NULL DEFAULT 1 "
        "CHECK (is_required IN (0, 1))"
    )
    op.execute("DROP TRIGGER trg_assignment_checklist_snapshot_immutable_update")
    op.execute(
        """
        CREATE TRIGGER trg_assignment_checklist_snapshot_immutable_update
        BEFORE UPDATE ON assignment_checklist_items
        WHEN NEW.id IS NOT OLD.id
          OR NEW.weekly_assignment_id IS NOT OLD.weekly_assignment_id
          OR NEW.label_snapshot IS NOT OLD.label_snapshot
          OR NEW.position IS NOT OLD.position
          OR NEW.is_required IS NOT OLD.is_required
        BEGIN
            SELECT RAISE(ABORT, 'assignment checklist snapshots are immutable');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_assignment_checklist_snapshot_immutable_update")
    op.execute(
        """
        CREATE TRIGGER trg_assignment_checklist_snapshot_immutable_update
        BEFORE UPDATE ON assignment_checklist_items
        WHEN NEW.id IS NOT OLD.id
          OR NEW.weekly_assignment_id IS NOT OLD.weekly_assignment_id
          OR NEW.label_snapshot IS NOT OLD.label_snapshot
          OR NEW.position IS NOT OLD.position
        BEGIN
            SELECT RAISE(ABORT, 'assignment checklist snapshots are immutable');
        END
        """
    )
    op.execute("ALTER TABLE assignment_checklist_items DROP COLUMN is_required")
    op.execute("ALTER TABLE chore_checklist_items DROP COLUMN is_required")
