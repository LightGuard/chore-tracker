"""Add immutable one-day claims for unassigned chores.

Revision ID: 0012_daily_chore_claims
Revises: 0011_chore_weights
"""

from __future__ import annotations

from alembic import op

revision = "0012_daily_chore_claims"
down_revision = "0011_chore_weights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A claim is a one-day assignment record for a chore that the weekly
    # rotation did not assign for that Monday-Sunday week. The unique
    # (chore_id, claim_date) pair is what makes competing claims safe: exactly
    # one child can hold a chore for a day, regardless of request interleaving.
    op.execute(
        """
        CREATE TABLE daily_chore_claims (
            id INTEGER PRIMARY KEY,
            family_member_id INTEGER NOT NULL
                REFERENCES family_members(id) ON DELETE RESTRICT,
            chore_id INTEGER NOT NULL
                REFERENCES chores(id) ON DELETE RESTRICT,
            claim_date TEXT NOT NULL,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            chore_name_snapshot TEXT NOT NULL,
            chore_description_snapshot TEXT NOT NULL DEFAULT '',
            chore_weight_snapshot INTEGER NOT NULL DEFAULT 1
                CHECK (typeof(chore_weight_snapshot) = 'integer'
                       AND chore_weight_snapshot BETWEEN 0 AND 10),
            claimed_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (date(claim_date) IS NOT NULL),
            CHECK (date(week_start) IS NOT NULL),
            CHECK (strftime('%w', week_start) = '1'),
            CHECK (week_end = date(week_start, '+6 days')),
            CHECK (claim_date >= week_start AND claim_date <= week_end),
            CHECK (length(trim(chore_name_snapshot)) > 0),
            UNIQUE (chore_id, claim_date)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_chore_claims_member_date "
        "ON daily_chore_claims(family_member_id, claim_date)"
    )
    op.execute(
        """
        CREATE TRIGGER trg_daily_chore_claims_immutable_update
        BEFORE UPDATE ON daily_chore_claims
        BEGIN
            SELECT RAISE(ABORT, 'daily chore claims are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_daily_chore_claims_immutable_delete
        BEFORE DELETE ON daily_chore_claims
        BEGIN
            SELECT RAISE(ABORT, 'daily chore claims cannot be deleted');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_daily_chore_claims_immutable_delete")
    op.execute("DROP TRIGGER trg_daily_chore_claims_immutable_update")
    op.execute("DROP INDEX ix_daily_chore_claims_member_date")
    op.execute("DROP TABLE daily_chore_claims")
