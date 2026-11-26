"""Add reward-neutral chore weights and assignment weight snapshots.

Revision ID: 0011_chore_weights
Revises: 0010_weekly_report_rewards
"""

from __future__ import annotations

from alembic import op

revision = "0011_chore_weights"
down_revision = "0010_weekly_report_rewards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A weight of 1 is the documented compatible default: existing chores and
    # existing assignment snapshots keep today's reward baseline, and the
    # consuming frontends decide how weight maps to their own rewards.
    op.execute(
        "ALTER TABLE chores ADD COLUMN weight INTEGER NOT NULL DEFAULT 1 "
        "CHECK (typeof(weight) = 'integer' AND weight BETWEEN 0 AND 10)"
    )
    op.execute(
        "ALTER TABLE weekly_assignments ADD COLUMN chore_weight_snapshot "
        "INTEGER NOT NULL DEFAULT 1 "
        "CHECK (typeof(chore_weight_snapshot) = 'integer' "
        "AND chore_weight_snapshot BETWEEN 0 AND 10)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE weekly_assignments DROP COLUMN chore_weight_snapshot")
    op.execute("ALTER TABLE chores DROP COLUMN weight")
