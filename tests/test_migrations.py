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
            "assignment_checklist_items",
            "daily_checklist_completions",
            "weekly_reports",
            "report_deliveries",
            "alembic_version",
        } <= tables
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()["version_num"]
        assert revision == "0003_immutable_assignment_history"


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
            INSERT INTO weekly_reports (week_start, week_end, report_snapshot_json)
            VALUES ('2026-11-09', '2026-11-15', '{}')
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
            assert "same chore" in str(error)
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
