"""Integration tests for the versioned SQLite schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from chore_tracker.adapters.sqlite import connect

ROOT = Path(__file__).resolve().parents[1]


def migration_config(database_path: Path) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    return config


def read_connection(database_path: Path) -> sqlite3.Connection:
    return connect(database_path)


def test_fresh_database_is_created_entirely_by_migrations(tmp_path) -> None:
    database_path = tmp_path / "fresh.db"

    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "administrators",
            "family_members",
            "chores",
            "chore_checklist_items",
            "weekly_assignments",
            "assignment_rotation_state",
            "weekly_assignment_generations",
            "assignment_checklist_items",
            "daily_checklist_completions",
            "weekly_reports",
            "weekly_report_entries",
            "weekly_report_days",
            "weekly_report_rewards",
            "weekly_rollover_state",
            "report_deliveries",
            "administrator_passkey_credentials",
            "authentication_challenges",
            "administrator_enrollment_tokens",
            "administrator_sessions",
            "alembic_version",
        } <= tables
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()["version_num"]
        assert revision == "0011_chore_weights"


def test_upgrade_from_prior_revision_preserves_existing_rows(tmp_path) -> None:
    database_path = tmp_path / "upgrade.db"
    config = migration_config(database_path)

    command.upgrade(config, "0001_core_entities")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean kitchen')"
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        member = connection.execute(
            "SELECT display_name FROM family_members WHERE id = 1"
        ).fetchone()
        chore = connection.execute("SELECT name FROM chores WHERE id = 1").fetchone()
        assert member["display_name"] == "Taylor"
        assert chore["name"] == "Kitchen"
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == 0
        )


def test_assignment_snapshots_and_completion_survive_definition_changes(
    tmp_path,
) -> None:
    database_path = tmp_path / "history.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute(
            """
            INSERT INTO chores (name, description)
            VALUES ('Kitchen', 'Original description')
            """
        )
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position)
            VALUES (1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15',
                    'Kitchen', 'Original description')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position
            )
            VALUES (1, 1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (1, '2026-11-09', 1, '2026-11-09T18:00:00Z')
            """
        )
        connection.execute(
            """
            UPDATE family_members
            SET display_name = 'Taylor P.', is_active = 0
            WHERE id = 1
            """
        )
        connection.execute(
            """
            UPDATE chores
            SET name = 'Kitchen v2', description = 'Updated description',
                is_active = 0
            WHERE id = 1
            """
        )
        connection.execute("DELETE FROM chore_checklist_items WHERE id = 1")

        assignment = connection.execute(
            """
            SELECT chore_name_snapshot, chore_description_snapshot
            FROM weekly_assignments WHERE id = 1
            """
        ).fetchone()
        snapshot_item = connection.execute(
            """
            SELECT label_snapshot, source_checklist_item_id
            FROM assignment_checklist_items WHERE id = 1
            """
        ).fetchone()
        completion = connection.execute(
            """
            SELECT is_completed, completion_date
            FROM daily_checklist_completions
            WHERE assignment_checklist_item_id = 1
            """
        ).fetchone()

        assert assignment["chore_name_snapshot"] == "Kitchen"
        assert assignment["chore_description_snapshot"] == "Original description"
        assert snapshot_item["label_snapshot"] == "Wipe counters"
        assert snapshot_item["source_checklist_item_id"] is None
        assert completion["is_completed"] == 1
        assert completion["completion_date"] == "2026-11-09"
        assert (
            connection.execute(
                "SELECT is_active FROM family_members WHERE id = 1"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT is_active FROM chores WHERE id = 1").fetchone()[
                0
            ]
            == 0
        )


def test_completion_date_must_be_within_assignment_week(tmp_path) -> None:
    database_path = tmp_path / "date-boundary.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute("INSERT INTO chores (name) VALUES ('Kitchen')")
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15', 'Kitchen')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, label_snapshot, position
            )
            VALUES (1, 'Wipe counters', 0)
            """
        )

        try:
            connection.execute(
                """
                INSERT INTO daily_checklist_completions (
                    assignment_checklist_item_id, completion_date
                )
                VALUES (1, '2026-11-16')
                """
            )
        except sqlite3.IntegrityError as error:
            assert "within assignment week" in str(error)
        else:
            raise AssertionError("Out-of-week completion date was accepted")


def test_report_delivery_is_unique_per_administrator_and_report(tmp_path) -> None:
    database_path = tmp_path / "report-delivery.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO administrators (email) VALUES ('admin@example.test')"
        )
        connection.execute(
            """
            INSERT INTO weekly_reports (week_start, week_end)
            VALUES ('2026-11-09', '2026-11-15')
            """
        )
        connection.execute(
            """
            INSERT INTO report_deliveries (report_id, administrator_id)
            VALUES (1, 1)
            """
        )

        try:
            connection.execute(
                """
                INSERT INTO report_deliveries (report_id, administrator_id)
                VALUES (1, 1)
                """
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Duplicate report delivery state was accepted")


def test_weekly_rollover_state_is_singleton_and_monotonic(tmp_path) -> None:
    database_path = tmp_path / "rollover-state.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO weekly_rollover_state (
                id, last_completed_week_start, completed_at
            )
            VALUES (1, '2026-11-09', '2026-11-09T10:00:00Z')
            """
        )

        try:
            connection.execute(
                """
                INSERT INTO weekly_rollover_state (
                    id, last_completed_week_start, completed_at
                )
                VALUES (2, '2026-11-16', '2026-11-16T10:00:00Z')
                """
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("A second rollover checkpoint row was accepted")

        try:
            connection.execute(
                """
                UPDATE weekly_rollover_state
                SET last_completed_week_start = '2026-11-02'
                WHERE id = 1
                """
            )
        except sqlite3.IntegrityError as error:
            assert "cannot move backwards" in str(error)
        else:
            raise AssertionError("The rollover checkpoint was allowed to regress")

        connection.execute(
            """
            UPDATE weekly_rollover_state
            SET last_completed_week_start = '2026-11-16'
            WHERE id = 1
            """
        )
        assert (
            connection.execute(
                "SELECT last_completed_week_start FROM weekly_rollover_state"
            ).fetchone()[0]
            == "2026-11-16"
        )

        try:
            connection.execute("DELETE FROM weekly_rollover_state")
        except sqlite3.IntegrityError as error:
            assert "cannot be deleted" in str(error)
        else:
            raise AssertionError("The rollover checkpoint was deleted")


def test_assignment_history_is_immutable_and_source_items_match_chore(tmp_path) -> None:
    database_path = tmp_path / "immutable-history.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute("INSERT INTO chores (name) VALUES ('Kitchen')")
        connection.execute("INSERT INTO chores (name) VALUES ('Bathroom')")
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position)
            VALUES (1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position)
            VALUES (2, 'Clean mirror', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15', 'Kitchen', '')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position
            )
            VALUES (1, 1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (1, '2026-11-09', 1, '2026-11-09T18:00:00Z')
            """
        )

        prohibited_assignment_updates = (
            "UPDATE weekly_assignments SET week_start = '2026-11-10' WHERE id = 1",
            "UPDATE weekly_assignments SET week_end = '2026-11-16' WHERE id = 1",
            "UPDATE weekly_assignments SET chore_id = 2 WHERE id = 1",
            "UPDATE weekly_assignments SET family_member_id = 2 WHERE id = 1",
            (
                "UPDATE weekly_assignments SET chore_name_snapshot = 'Bathroom' "
                "WHERE id = 1"
            ),
            (
                "UPDATE weekly_assignments SET chore_description_snapshot = 'Changed' "
                "WHERE id = 1"
            ),
        )
        for statement in prohibited_assignment_updates:
            try:
                connection.execute(statement)
            except sqlite3.IntegrityError as error:
                assert "immutable" in str(error)
            else:
                raise AssertionError(
                    f"Prohibited assignment update succeeded: {statement}"
                )

        for statement in (
            "DELETE FROM weekly_assignments WHERE id = 1",
            (
                "UPDATE assignment_checklist_items SET label_snapshot = 'Changed' "
                "WHERE id = 1"
            ),
            "UPDATE assignment_checklist_items SET position = 1 WHERE id = 1",
            "DELETE FROM assignment_checklist_items WHERE id = 1",
        ):
            try:
                connection.execute(statement)
            except sqlite3.IntegrityError as error:
                assert "immutable" in str(error) or "cannot be deleted" in str(error)
            else:
                raise AssertionError(
                    f"Prohibited snapshot operation succeeded: {statement}"
                )

        try:
            connection.execute(
                """
                INSERT INTO assignment_checklist_items (
                    weekly_assignment_id, source_checklist_item_id,
                    label_snapshot, position
                )
                VALUES (1, 2, 'Clean mirror', 1)
                """
            )
        except sqlite3.IntegrityError as error:
            assert "assigned chore" in str(error)
        else:
            raise AssertionError("A source item from another chore was accepted")

        try:
            connection.execute(
                """
                UPDATE assignment_checklist_items
                SET source_checklist_item_id = 2
                WHERE id = 1
                """
            )
        except sqlite3.IntegrityError as error:
            assert "assigned chore" in str(error)
        else:
            raise AssertionError("A cross-chore source-item update was accepted")

        try:
            connection.execute(
                "UPDATE chore_checklist_items SET chore_id = 2 WHERE id = 1"
            )
        except sqlite3.IntegrityError as error:
            assert "cannot move a checklist item" in str(error)
        else:
            raise AssertionError("A referenced source item was moved to another chore")

        completion = connection.execute(
            """
            SELECT completion_date, is_completed
            FROM daily_checklist_completions
            WHERE assignment_checklist_item_id = 1
            """
        ).fetchone()
        assert completion["completion_date"] == "2026-11-09"
        assert completion["is_completed"] == 1


def test_deleting_source_catalog_item_preserves_snapshot_and_completion(
    tmp_path,
) -> None:
    database_path = tmp_path / "source-delete.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute("INSERT INTO chores (name) VALUES ('Kitchen')")
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position)
            VALUES (1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15', 'Kitchen')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position
            )
            VALUES (1, 1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (1, '2026-11-09', 1, '2026-11-09T18:00:00Z')
            """
        )

        connection.execute("DELETE FROM chore_checklist_items WHERE id = 1")

        snapshot = connection.execute(
            """
            SELECT label_snapshot, source_checklist_item_id
            FROM assignment_checklist_items WHERE id = 1
            """
        ).fetchone()
        completion_count = connection.execute(
            """
            SELECT COUNT(*) FROM daily_checklist_completions
            WHERE assignment_checklist_item_id = 1
            """
        ).fetchone()[0]

        assert snapshot["label_snapshot"] == "Wipe counters"
        assert snapshot["source_checklist_item_id"] is None
        assert completion_count == 1


def test_immutable_history_migration_preserves_existing_assignment_data(
    tmp_path,
) -> None:
    database_path = tmp_path / "preserve-history.db"
    config = migration_config(database_path)
    command.upgrade(config, "0002_assignments_completion_reports")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute("INSERT INTO chores (name) VALUES ('Kitchen')")
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position)
            VALUES (1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15', 'Kitchen')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position
            )
            VALUES (1, 1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (1, '2026-11-09', 1, '2026-11-09T18:00:00Z')
            """
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        assignment = connection.execute(
            "SELECT chore_name_snapshot FROM weekly_assignments WHERE id = 1"
        ).fetchone()
        snapshot = connection.execute(
            "SELECT label_snapshot FROM assignment_checklist_items WHERE id = 1"
        ).fetchone()
        completion = connection.execute(
            """
            SELECT completion_date, is_completed
            FROM daily_checklist_completions
            WHERE assignment_checklist_item_id = 1
            """
        ).fetchone()

        assert assignment["chore_name_snapshot"] == "Kitchen"
        assert snapshot["label_snapshot"] == "Wipe counters"
        assert completion["completion_date"] == "2026-11-09"
        assert completion["is_completed"] == 1


def test_report_migration_preserves_existing_report_and_delivery_rows(
    tmp_path,
) -> None:
    database_path = tmp_path / "report-upgrade.db"
    config = migration_config(database_path)
    command.upgrade(config, "0005_weekly_assignment_generation")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO administrators (email) VALUES ('admin@example.test')"
        )
        connection.execute(
            """
            INSERT INTO weekly_reports (week_start, week_end, report_snapshot_json)
            VALUES ('2026-11-09', '2026-11-15', '{"legacy": true}')
            """
        )
        connection.execute(
            """
            INSERT INTO report_deliveries (report_id, administrator_id)
            VALUES (1, 1)
            """
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(weekly_reports)")
        }
        report = connection.execute(
            """
            SELECT id, week_start, week_end, family_member_count,
                   total_days, completed_days, incomplete_days
            FROM weekly_reports
            """
        ).fetchone()
        delivery = connection.execute(
            "SELECT report_id, administrator_id FROM report_deliveries"
        ).fetchone()

    assert "report_snapshot_json" not in columns
    assert dict(report) == {
        "id": 1,
        "week_start": "2026-11-09",
        "week_end": "2026-11-15",
        "family_member_count": 0,
        "total_days": 0,
        "completed_days": 0,
        "incomplete_days": 0,
    }
    assert dict(delivery) == {"report_id": 1, "administrator_id": 1}


def test_theme_preferences_are_nullable_and_downgrade_removes_them(tmp_path) -> None:
    database_path = tmp_path / "theme-preferences.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute(
            "INSERT INTO administrators (email) VALUES ('admin@example.test')"
        )
        member = connection.execute(
            "SELECT theme_id FROM family_members WHERE id = 1"
        ).fetchone()
        administrator = connection.execute(
            "SELECT theme_id FROM administrators WHERE id = 1"
        ).fetchone()
        assert member["theme_id"] is None
        assert administrator["theme_id"] is None

    command.downgrade(config, "0007_weekly_rollover_state")
    with read_connection(database_path) as connection:
        member_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(family_members)")
        }
        admin_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(administrators)")
        }
        assert "theme_id" not in member_columns
        assert "theme_id" not in admin_columns
        assert (
            connection.execute(
                "SELECT display_name FROM family_members WHERE id = 1"
            ).fetchone()["display_name"]
            == "Taylor"
        )


def test_optional_checklist_flags_default_to_required_for_existing_rows(
    tmp_path,
) -> None:
    database_path = tmp_path / "optional-backfill.db"
    config = migration_config(database_path)
    command.upgrade(config, "0008_theme_preferences")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean')"
        )
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position)
            VALUES (1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15', 'Kitchen', 'Clean')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position
            )
            VALUES (1, 1, 'Wipe counters', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (1, '2026-11-09', 1, '2026-11-09T18:00:00Z')
            """
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        chore_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(chore_checklist_items)")
        }
        snapshot_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(assignment_checklist_items)"
            )
        }
        chore_item = connection.execute(
            "SELECT is_required FROM chore_checklist_items WHERE id = 1"
        ).fetchone()
        snapshot_item = connection.execute(
            "SELECT is_required FROM assignment_checklist_items WHERE id = 1"
        ).fetchone()
        completion = connection.execute(
            """
            SELECT is_completed, completion_date
            FROM daily_checklist_completions
            WHERE assignment_checklist_item_id = 1
            """
        ).fetchone()

    assert "is_required" in chore_columns
    assert "is_required" in snapshot_columns
    assert chore_item["is_required"] == 1
    assert snapshot_item["is_required"] == 1
    assert dict(completion) == {
        "is_completed": 1,
        "completion_date": "2026-11-09",
    }


def test_optional_snapshot_flag_survives_definition_edits_and_is_immutable(
    tmp_path,
) -> None:
    database_path = tmp_path / "optional-snapshot.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean')"
        )
        connection.execute(
            """
            INSERT INTO chore_checklist_items (
                chore_id, label, position, is_required
            )
            VALUES (1, 'Wipe counters', 0, 0)
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (1, 1, '2026-11-09', '2026-11-15', 'Kitchen', 'Clean')
            """
        )
        connection.execute(
            """
            INSERT INTO assignment_checklist_items (
                weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position, is_required
            )
            VALUES (1, 1, 'Wipe counters', 0, 0)
            """
        )
        connection.execute(
            """
            UPDATE chore_checklist_items
            SET label = 'Wipe all counters', is_required = 1
            WHERE id = 1
            """
        )
        snapshot = connection.execute(
            """
            SELECT label_snapshot, is_required
            FROM assignment_checklist_items WHERE id = 1
            """
        ).fetchone()
        assert dict(snapshot) == {
            "label_snapshot": "Wipe counters",
            "is_required": 0,
        }

        try:
            connection.execute(
                "UPDATE assignment_checklist_items SET is_required = 1 WHERE id = 1"
            )
        except sqlite3.IntegrityError as error:
            assert "immutable" in str(error)
        else:
            raise AssertionError("Optional snapshot flag was mutable")


def test_weekly_report_rewards_are_unique_per_entry_and_removed_on_downgrade(
    tmp_path,
) -> None:
    database_path = tmp_path / "report-rewards.db"
    config = migration_config(database_path)
    command.upgrade(config, "0009_optional_checklist_items")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO administrators (email) VALUES ('admin@example.test')"
        )
        connection.execute("INSERT INTO family_members (display_name) VALUES ('Alex')")
        connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean')"
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (1, 1, '2026-11-16', '2026-11-22', 'Kitchen', 'Clean')
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_reports (
                week_start, week_end, family_member_count, total_days,
                completed_days, incomplete_days, generated_at, finalized_at
            )
            VALUES (
                '2026-11-16', '2026-11-22', 1, 7, 7, 0,
                '2026-11-23T10:00:00Z', '2026-11-23T10:00:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO weekly_report_entries (
                report_id, weekly_assignment_id, position, family_member_id,
                family_member_name_snapshot, chore_name_snapshot,
                chore_description_snapshot, completed_days, incomplete_days
            )
            VALUES (1, 1, 0, 1, 'Alex', 'Kitchen', 'Clean', 7, 0)
            """
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        # Existing report data survives the additive migration unchanged.
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0] == 1
        )
        entry = connection.execute(
            """
            SELECT family_member_name_snapshot, completed_days
            FROM weekly_report_entries
            WHERE id = 1
            """
        ).fetchone()
        assert dict(entry) == {
            "family_member_name_snapshot": "Alex",
            "completed_days": 7,
        }
        connection.execute(
            """
            INSERT INTO weekly_report_rewards (
                weekly_report_entry_id, rewarded_at,
                rewarded_by_administrator_id
            )
            VALUES (1, '2026-11-23T11:00:00Z', 1)
            """
        )

    with read_connection(database_path) as connection:
        reward = connection.execute(
            """
            SELECT weekly_report_entry_id, rewarded_at,
                   rewarded_by_administrator_id
            FROM weekly_report_rewards
            """
        ).fetchone()
        assert dict(reward) == {
            "weekly_report_entry_id": 1,
            "rewarded_at": "2026-11-23T11:00:00Z",
            "rewarded_by_administrator_id": 1,
        }
        for statement, label in (
            (
                """
                INSERT INTO weekly_report_rewards (
                    weekly_report_entry_id, rewarded_at,
                    rewarded_by_administrator_id
                )
                VALUES (1, '2026-11-23T12:00:00Z', 1)
                """,
                "duplicate rewards must be rejected",
            ),
            (
                """
                INSERT INTO weekly_report_rewards (
                    weekly_report_entry_id, rewarded_at,
                    rewarded_by_administrator_id
                )
                VALUES (999, '2026-11-23T12:00:00Z', 1)
                """,
                "rewards must reference an existing entry",
            ),
            (
                "UPDATE weekly_report_rewards SET rewarded_at = '2026-11-24T00:00:00Z'",
                "rewards must be immutable",
            ),
            ("DELETE FROM weekly_report_rewards", "rewards cannot be deleted"),
        ):
            try:
                connection.execute(statement)
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError(label)

    command.downgrade(config, "0009_optional_checklist_items")

    with read_connection(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "weekly_report_rewards" not in tables
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0] == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_entries").fetchone()[
                0
            ]
            == 1
        )


def test_chore_weights_default_to_one_and_downgrade_removes_them(tmp_path) -> None:
    database_path = tmp_path / "chore-weights.db"
    config = migration_config(database_path)
    command.upgrade(config, "0010_weekly_report_rewards")

    with read_connection(database_path) as connection:
        connection.execute("INSERT INTO family_members (display_name) VALUES ('Alex')")
        connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean')"
        )
        connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (1, 1, '2026-11-16', '2026-11-22', 'Kitchen', 'Clean')
            """
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        chore = connection.execute(
            "SELECT name, weight FROM chores WHERE id = 1"
        ).fetchone()
        assignment = connection.execute(
            "SELECT chore_weight_snapshot FROM weekly_assignments"
        ).fetchone()
        assert dict(chore) == {"name": "Kitchen", "weight": 1}
        assert assignment["chore_weight_snapshot"] == 1

        connection.execute("UPDATE chores SET weight = 10 WHERE id = 1")
        try:
            connection.execute(
                "INSERT INTO chores (name, description, weight) "
                "VALUES ('Too heavy', 'Invalid', 11)"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("chore weight above the maximum must be rejected")
        try:
            connection.execute(
                "INSERT INTO weekly_assignments ("
                "family_member_id, chore_id, week_start, week_end, "
                "chore_name_snapshot, chore_description_snapshot, "
                "chore_weight_snapshot) "
                "VALUES (1, 1, '2026-11-23', '2026-11-29', 'Kitchen', "
                "'Clean', -1)"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("assignment weight below the minimum must be rejected")
        try:
            connection.execute(
                "INSERT INTO chores (name, description, weight) "
                "VALUES ('Fractional', 'Invalid', 2.5)"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("fractional chore weights must be rejected")

    command.downgrade(config, "0010_weekly_report_rewards")

    with read_connection(database_path) as connection:
        chore_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(chores)")
        }
        assignment_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(weekly_assignments)")
        }
        assert "weight" not in chore_columns
        assert "chore_weight_snapshot" not in assignment_columns
        assert (
            connection.execute("SELECT name FROM chores WHERE id = 1").fetchone()[
                "name"
            ]
            == "Kitchen"
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == 1
        )
