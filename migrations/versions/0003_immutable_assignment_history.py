"""Protect weekly assignment and checklist history from mutation.

Revision ID: 0003_immutable_assignment_history
Revises: 0002_assignments_completion_reports
"""

from __future__ import annotations

from alembic import op

revision = "0003_immutable_assignment_history"
down_revision = "0002_assignments_completion_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER trg_weekly_assignments_immutable_update
        BEFORE UPDATE ON weekly_assignments
        BEGIN
            SELECT RAISE(ABORT, 'weekly assignments are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_assignments_immutable_delete
        BEFORE DELETE ON weekly_assignments
        BEGIN
            SELECT RAISE(ABORT, 'weekly assignments cannot be deleted');
        END
        """
    )
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
    op.execute(
        """
        CREATE TRIGGER trg_assignment_checklist_snapshot_immutable_delete
        BEFORE DELETE ON assignment_checklist_items
        BEGIN
            SELECT RAISE(ABORT, 'assignment checklist snapshots cannot be deleted');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_assignment_checklist_source_chore_insert
        BEFORE INSERT ON assignment_checklist_items
        WHEN NEW.source_checklist_item_id IS NOT NULL
         AND NOT EXISTS (
            SELECT 1
            FROM chore_checklist_items AS source_item
            JOIN weekly_assignments AS assignment
              ON assignment.chore_id = source_item.chore_id
            WHERE source_item.id = NEW.source_checklist_item_id
              AND assignment.id = NEW.weekly_assignment_id
         )
        BEGIN
            SELECT RAISE(
                ABORT,
                'source checklist item must belong to the assigned chore'
            );
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_assignment_checklist_source_chore_update
        BEFORE UPDATE OF source_checklist_item_id, weekly_assignment_id
        ON assignment_checklist_items
        WHEN NEW.source_checklist_item_id IS NOT NULL
         AND NOT EXISTS (
            SELECT 1
            FROM chore_checklist_items AS source_item
            JOIN weekly_assignments AS assignment
              ON assignment.chore_id = source_item.chore_id
            WHERE source_item.id = NEW.source_checklist_item_id
              AND assignment.id = NEW.weekly_assignment_id
         )
        BEGIN
            SELECT RAISE(
                ABORT,
                'source checklist item must belong to the assigned chore'
            );
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_chore_checklist_item_chore_consistency_update
        BEFORE UPDATE OF chore_id ON chore_checklist_items
        WHEN EXISTS (
            SELECT 1
            FROM assignment_checklist_items AS snapshot_item
            JOIN weekly_assignments AS assignment
              ON assignment.id = snapshot_item.weekly_assignment_id
            WHERE snapshot_item.source_checklist_item_id = OLD.id
              AND assignment.chore_id != NEW.chore_id
        )
        BEGIN
            SELECT RAISE(
                ABORT,
                'cannot move a checklist item referenced by another chore assignment'
            );
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_chore_checklist_item_chore_consistency_update")
    op.execute("DROP TRIGGER trg_assignment_checklist_source_chore_update")
    op.execute("DROP TRIGGER trg_assignment_checklist_source_chore_insert")
    op.execute("DROP TRIGGER trg_assignment_checklist_snapshot_immutable_delete")
    op.execute("DROP TRIGGER trg_assignment_checklist_snapshot_immutable_update")
    op.execute("DROP TRIGGER trg_weekly_assignments_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_assignments_immutable_update")
