"""Add completion state for one-day chore claims.

Revision ID: 0013_claim_completions
Revises: 0012_daily_chore_claims

A claim is a one-day assignment record, so its done state lives in its own
append/update-only table rather than on the immutable claim row. Derived Quest
XP reads the claim's chore weight snapshot through this table; nothing rewrites
the claim, the weekly assignment, or any completion history.
"""

from __future__ import annotations

from alembic import op

revision = "0013_claim_completions"
down_revision = "0012_daily_chore_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per claim: the claim already names exactly one local date, so the
    # primary key doubles as the (claim, date) uniqueness that completion rows
    # need. Unchecking a chore updates this row; nothing is ever deleted.
    op.execute(
        """
        CREATE TABLE daily_chore_claim_completions (
            claim_id INTEGER PRIMARY KEY
                REFERENCES daily_chore_claims(id) ON DELETE RESTRICT,
            is_completed INTEGER NOT NULL DEFAULT 0
                CHECK (is_completed IN (0, 1)),
            completed_at TEXT,
            CHECK (
                (is_completed = 0 AND completed_at IS NULL)
                OR (is_completed = 1 AND completed_at IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claim_completions_immutable_delete
        BEFORE DELETE ON daily_chore_claim_completions
        BEGIN
            SELECT RAISE(ABORT, 'claim completions cannot be deleted');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_claim_completions_immutable_delete")
    op.execute("DROP TABLE daily_chore_claim_completions")
