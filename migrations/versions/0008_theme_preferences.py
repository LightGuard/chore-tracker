"""Add nullable theme preferences for family members and administrators.

Revision ID: 0008_theme_preferences
Revises: 0007_weekly_rollover_state
"""

from __future__ import annotations

from alembic import op

revision = "0008_theme_preferences"
down_revision = "0007_weekly_rollover_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows stay unset. The frontend applies the Homestead default;
    # the API deliberately returns the raw saved value, including NULL.
    op.execute("ALTER TABLE family_members ADD COLUMN theme_id TEXT")
    op.execute("ALTER TABLE administrators ADD COLUMN theme_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE administrators DROP COLUMN theme_id")
    op.execute("ALTER TABLE family_members DROP COLUMN theme_id")
