"""Add weekly assignments, immutable chore snapshots, completion, and reports.

Revision ID: 0002_assignments_completion_reports
Revises: 0001_core_entities
"""

from __future__ import annotations

from alembic import op

revision = "0002_assignments_completion_reports"
down_revision = "0001_core_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE weekly_assignments (
            id INTEGER PRIMARY KEY,
            family_member_id INTEGER NOT NULL
                REFERENCES family_members(id) ON DELETE RESTRICT,
            chore_id INTEGER NOT NULL
                REFERENCES chores(id) ON DELETE RESTRICT,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            chore_name_snapshot TEXT NOT NULL,
            chore_description_snapshot TEXT NOT NULL DEFAULT '',
            assigned_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (date(week_start) IS NOT NULL),
            CHECK (strftime('%w', week_start) = '1'),
            CHECK (week_end = date(week_start, '+6 days')),
            CHECK (length(trim(chore_name_snapshot)) > 0),
            UNIQUE (family_member_id, week_start)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_weekly_assignments_week "
        "ON weekly_assignments(week_start, week_end)"
    )
    op.execute(
        "CREATE INDEX ix_weekly_assignments_chore "
        "ON weekly_assignments(chore_id, week_start)"
    )
    op.execute(
        """
        CREATE TABLE assignment_checklist_items (
            id INTEGER PRIMARY KEY,
            weekly_assignment_id INTEGER NOT NULL
                REFERENCES weekly_assignments(id) ON DELETE RESTRICT,
            source_checklist_item_id INTEGER
                REFERENCES chore_checklist_items(id) ON DELETE SET NULL,
            label_snapshot TEXT NOT NULL,
            position INTEGER NOT NULL CHECK (position >= 0),
            CHECK (length(trim(label_snapshot)) > 0),
            UNIQUE (weekly_assignment_id, position)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE daily_checklist_completions (
            assignment_checklist_item_id INTEGER NOT NULL
                REFERENCES assignment_checklist_items(id) ON DELETE RESTRICT,
            completion_date TEXT NOT NULL,
            is_completed INTEGER NOT NULL DEFAULT 0
                CHECK (is_completed IN (0, 1)),
            completed_at TEXT,
            CHECK (date(completion_date) IS NOT NULL),
            CHECK (
                (is_completed = 0 AND completed_at IS NULL)
                OR (is_completed = 1 AND completed_at IS NOT NULL)
            ),
            PRIMARY KEY (assignment_checklist_item_id, completion_date)
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_completion_within_assignment_week_insert
        BEFORE INSERT ON daily_checklist_completions
        BEGIN
            SELECT CASE
                WHEN NEW.completion_date < (
                    SELECT wa.week_start
                    FROM assignment_checklist_items AS aci
                    JOIN weekly_assignments AS wa
                      ON wa.id = aci.weekly_assignment_id
                    WHERE aci.id = NEW.assignment_checklist_item_id
                )
                OR NEW.completion_date > (
                    SELECT wa.week_end
                    FROM assignment_checklist_items AS aci
                    JOIN weekly_assignments AS wa
                      ON wa.id = aci.weekly_assignment_id
                    WHERE aci.id = NEW.assignment_checklist_item_id
                )
                THEN RAISE(ABORT, 'completion date must be within assignment week')
            END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_completion_within_assignment_week_update
        BEFORE UPDATE OF assignment_checklist_item_id, completion_date
        ON daily_checklist_completions
        BEGIN
            SELECT CASE
                WHEN NEW.completion_date < (
                    SELECT wa.week_start
                    FROM assignment_checklist_items AS aci
                    JOIN weekly_assignments AS wa
                      ON wa.id = aci.weekly_assignment_id
                    WHERE aci.id = NEW.assignment_checklist_item_id
                )
                OR NEW.completion_date > (
                    SELECT wa.week_end
                    FROM assignment_checklist_items AS aci
                    JOIN weekly_assignments AS wa
                      ON wa.id = aci.weekly_assignment_id
                    WHERE aci.id = NEW.assignment_checklist_item_id
                )
                THEN RAISE(ABORT, 'completion date must be within assignment week')
            END;
        END
        """
    )
    op.execute(
        """
        CREATE TABLE weekly_reports (
            id INTEGER PRIMARY KEY,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            report_snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            finalized_at TEXT,
            CHECK (date(week_start) IS NOT NULL),
            CHECK (strftime('%w', week_start) = '1'),
            CHECK (week_end = date(week_start, '+6 days')),
            UNIQUE (week_start)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE report_deliveries (
            id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL
                REFERENCES weekly_reports(id) ON DELETE RESTRICT,
            administrator_id INTEGER NOT NULL
                REFERENCES administrators(id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sent', 'failed')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            last_attempt_at TEXT,
            delivered_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            CHECK (status != 'sent' OR delivered_at IS NOT NULL),
            UNIQUE (report_id, administrator_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE report_deliveries")
    op.execute("DROP TABLE weekly_reports")
    op.execute("DROP TRIGGER trg_completion_within_assignment_week_update")
    op.execute("DROP TRIGGER trg_completion_within_assignment_week_insert")
    op.execute("DROP TABLE daily_checklist_completions")
    op.execute("DROP TABLE assignment_checklist_items")
    op.execute("DROP INDEX ix_weekly_assignments_chore")
    op.execute("DROP INDEX ix_weekly_assignments_week")
    op.execute("DROP TABLE weekly_assignments")
