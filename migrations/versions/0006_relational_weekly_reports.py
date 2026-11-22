"""Persist immutable relational weekly completion reports.

Revision ID: 0006_relational_weekly_reports
Revises: 0005_weekly_assignment_generation
"""

from __future__ import annotations

from alembic import op

revision = "0006_relational_weekly_reports"
down_revision = "0005_weekly_assignment_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rebuild the report header so summaries are explicit columns instead of
    # living inside the original opaque JSON document. Existing report and
    # delivery rows keep their identifiers while the table is replaced.
    op.execute(
        """
        CREATE TABLE weekly_reports_new (
            id INTEGER PRIMARY KEY,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            family_member_count INTEGER NOT NULL DEFAULT 0
                CHECK (family_member_count >= 0),
            total_days INTEGER NOT NULL DEFAULT 0 CHECK (total_days >= 0),
            completed_days INTEGER NOT NULL DEFAULT 0 CHECK (completed_days >= 0),
            incomplete_days INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_days >= 0),
            generated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            finalized_at TEXT,
            CHECK (date(week_start) IS NOT NULL),
            CHECK (strftime('%w', week_start) = '1'),
            CHECK (week_end = date(week_start, '+6 days')),
            CHECK (total_days = family_member_count * 7),
            CHECK (completed_days + incomplete_days = total_days),
            UNIQUE (week_start)
        )
        """
    )
    op.execute(
        """
        INSERT INTO weekly_reports_new (
            id, week_start, week_end, generated_at, finalized_at
        )
        SELECT id, week_start, week_end, created_at, finalized_at
        FROM weekly_reports
        """
    )
    op.execute(
        """
        CREATE TABLE report_deliveries_new (
            id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL
                REFERENCES weekly_reports_new(id) ON DELETE RESTRICT,
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
    op.execute(
        """
        INSERT INTO report_deliveries_new (
            id, report_id, administrator_id, status, attempt_count,
            last_attempt_at, delivered_at, last_error, created_at, updated_at
        )
        SELECT id, report_id, administrator_id, status, attempt_count,
               last_attempt_at, delivered_at, last_error, created_at, updated_at
        FROM report_deliveries
        """
    )
    op.execute("DROP TABLE report_deliveries")
    op.execute("DROP TABLE weekly_reports")
    op.execute("ALTER TABLE weekly_reports_new RENAME TO weekly_reports")
    op.execute("ALTER TABLE report_deliveries_new RENAME TO report_deliveries")

    op.execute(
        """
        CREATE TABLE weekly_report_entries (
            id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL
                REFERENCES weekly_reports(id) ON DELETE RESTRICT,
            weekly_assignment_id INTEGER NOT NULL
                REFERENCES weekly_assignments(id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position >= 0),
            family_member_id INTEGER NOT NULL
                REFERENCES family_members(id) ON DELETE RESTRICT,
            family_member_name_snapshot TEXT NOT NULL
                CHECK (length(trim(family_member_name_snapshot)) > 0),
            chore_name_snapshot TEXT NOT NULL
                CHECK (length(trim(chore_name_snapshot)) > 0),
            chore_description_snapshot TEXT NOT NULL DEFAULT '',
            completed_days INTEGER NOT NULL CHECK (completed_days >= 0),
            incomplete_days INTEGER NOT NULL CHECK (incomplete_days >= 0),
            CHECK (completed_days + incomplete_days = 7),
            UNIQUE (report_id, weekly_assignment_id),
            UNIQUE (report_id, position)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE weekly_report_days (
            report_entry_id INTEGER NOT NULL
                REFERENCES weekly_report_entries(id) ON DELETE RESTRICT,
            report_date TEXT NOT NULL,
            day_index INTEGER NOT NULL CHECK (day_index BETWEEN 0 AND 6),
            status TEXT NOT NULL CHECK (status IN ('complete', 'incomplete')),
            CHECK (date(report_date) IS NOT NULL),
            PRIMARY KEY (report_entry_id, report_date),
            UNIQUE (report_entry_id, day_index)
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_reports_immutable_update
        BEFORE UPDATE ON weekly_reports
        BEGIN
            SELECT RAISE(ABORT, 'weekly reports are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_reports_immutable_delete
        BEFORE DELETE ON weekly_reports
        BEGIN
            SELECT RAISE(ABORT, 'weekly reports cannot be deleted');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_report_entries_immutable_update
        BEFORE UPDATE ON weekly_report_entries
        BEGIN
            SELECT RAISE(ABORT, 'weekly report entries are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_report_entries_immutable_delete
        BEFORE DELETE ON weekly_report_entries
        BEGIN
            SELECT RAISE(ABORT, 'weekly report entries cannot be deleted');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_report_days_immutable_update
        BEFORE UPDATE ON weekly_report_days
        BEGIN
            SELECT RAISE(ABORT, 'weekly report days are immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_report_days_immutable_delete
        BEFORE DELETE ON weekly_report_days
        BEGIN
            SELECT RAISE(ABORT, 'weekly report days cannot be deleted');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_weekly_report_days_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_report_days_immutable_update")
    op.execute("DROP TRIGGER trg_weekly_report_entries_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_report_entries_immutable_update")
    op.execute("DROP TRIGGER trg_weekly_reports_immutable_delete")
    op.execute("DROP TRIGGER trg_weekly_reports_immutable_update")
    op.execute("DROP TABLE weekly_report_days")
    op.execute("DROP TABLE weekly_report_entries")

    # Restore the legacy header shape. Normalized report detail cannot be
    # represented by the legacy JSON document, so downgrade records an empty
    # object while preserving report and delivery identity.
    op.execute(
        """
        CREATE TABLE weekly_reports_legacy (
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
        INSERT INTO weekly_reports_legacy (
            id, week_start, week_end, report_snapshot_json, created_at, finalized_at
        )
        SELECT id, week_start, week_end, '{}', generated_at, finalized_at
        FROM weekly_reports
        """
    )
    op.execute(
        """
        CREATE TABLE report_deliveries_legacy (
            id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL
                REFERENCES weekly_reports_legacy(id) ON DELETE RESTRICT,
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
    op.execute(
        """
        INSERT INTO report_deliveries_legacy (
            id, report_id, administrator_id, status, attempt_count,
            last_attempt_at, delivered_at, last_error, created_at, updated_at
        )
        SELECT id, report_id, administrator_id, status, attempt_count,
               last_attempt_at, delivered_at, last_error, created_at, updated_at
        FROM report_deliveries
        """
    )
    op.execute("DROP TABLE report_deliveries")
    op.execute("DROP TABLE weekly_reports")
    op.execute("ALTER TABLE weekly_reports_legacy RENAME TO weekly_reports")
    op.execute("ALTER TABLE report_deliveries_legacy RENAME TO report_deliveries")
