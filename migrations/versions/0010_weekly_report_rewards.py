"""Persist per-entry weekly report reward tracking.

Revision ID: 0010_weekly_report_rewards
Revises: 0009_optional_checklist_items
"""

from __future__ import annotations

from alembic import op

revision = "0010_weekly_report_rewards"
down_revision = "0009_optional_checklist_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One reward record per immutable report entry keeps the audit trail
    # separate from the report snapshot itself. The primary key makes repeated
    # marking requests idempotent: the first recorded action is preserved.
    op.execute(
        """
        CREATE TABLE weekly_report_rewards (
            weekly_report_entry_id INTEGER PRIMARY KEY
                REFERENCES weekly_report_entries(id) ON DELETE RESTRICT,
            rewarded_at TEXT NOT NULL,
            rewarded_by_administrator_id INTEGER NOT NULL
                REFERENCES administrators(id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_report_rewards_immutable_update
        BEFORE UPDATE ON weekly_report_rewards
        BEGIN
            SELECT RAISE(ABORT, 'weekly report rewards are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_report_rewards_immutable_delete
        BEFORE DELETE ON weekly_report_rewards
        BEGIN
            SELECT RAISE(ABORT, 'weekly report rewards cannot be deleted');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_weekly_report_rewards_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_report_rewards_immutable_update")
    op.execute("DROP TABLE weekly_report_rewards")
