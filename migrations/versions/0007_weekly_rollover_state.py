"""Persist the durable weekly rollover checkpoint.

Revision ID: 0007_weekly_rollover_state
Revises: 0006_relational_weekly_reports
"""

from __future__ import annotations

from alembic import op

revision = "0007_weekly_rollover_state"
down_revision = "0006_relational_weekly_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The scheduler records the newest week whose report and assignments were
    # both persisted. Restarts read this row instead of relying on a timer.
    op.execute(
        """
        CREATE TABLE weekly_rollover_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_completed_week_start TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            CHECK (date(last_completed_week_start) IS NOT NULL),
            CHECK (strftime('%w', last_completed_week_start) = '1'),
            CHECK (date(completed_at) IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_rollover_state_monotonic
        BEFORE UPDATE ON weekly_rollover_state
        WHEN NEW.last_completed_week_start < OLD.last_completed_week_start
        BEGIN
            SELECT RAISE(ABORT, 'weekly rollover state cannot move backwards');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_rollover_state_immutable_delete
        BEFORE DELETE ON weekly_rollover_state
        BEGIN
            SELECT RAISE(ABORT, 'weekly rollover state cannot be deleted');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_weekly_rollover_state_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_rollover_state_monotonic")
    op.execute("DROP TABLE weekly_rollover_state")
