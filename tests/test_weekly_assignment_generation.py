"""Integration tests for transactional weekly assignment generation."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from chore_tracker.adapters.sqlite import connect
from chore_tracker.application.services.weekly_assignment_generation import (
    generate_weekly_assignments,
)

ROOT = Path(__file__).resolve().parents[1]
FIRST_WEEK = date(2026, 11, 16)
GENERATED_ON = date(2026, 11, 11)


def _database(tmp_path: Path) -> Path:
    database_path = tmp_path / "assignments.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")

    with connect(database_path) as connection:
        connection.executemany(
            "INSERT INTO family_members (display_name, is_active) VALUES (?, 1)",
            [("Zoe",), ("Alex",)],
        )
        connection.executemany(
            """
            INSERT INTO chores (name, description, is_active)
            VALUES (?, ?, 1)
            """,
            [
                ("Kitchen", "Clean the kitchen"),
                ("Yard", "Maintain the yard"),
                ("Bathroom", "Clean the bathroom"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position, is_active)
            VALUES (?, ?, ?, 1)
            """,
            [
                (1, "Sweep floor", 0),
                (1, "Wipe counters", 1),
                (2, "Mow lawn", 0),
                (3, "Clean sink", 0),
            ],
        )
    return database_path


def _assignment_values(assignments):
    return [
        (
            assignment.family_member_id,
            assignment.chore_id,
            assignment.week_start,
            assignment.week_end,
        )
        for assignment in assignments
    ]


def test_generation_normalizes_week_and_uses_deterministic_rotation(tmp_path):
    database_path = _database(tmp_path)

    assignments = generate_weekly_assignments(
        date(2026, 11, 18),
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=GENERATED_ON,
    )

    assert _assignment_values(assignments) == [
        (2, 3, FIRST_WEEK, date(2026, 11, 22)),
        (1, 1, FIRST_WEEK, date(2026, 11, 22)),
    ]
    assert [item.label for item in assignments[1].checklist_items] == [
        "Sweep floor",
        "Wipe counters",
    ]
    assert [item.position for item in assignments[1].checklist_items] == [0, 1]

    with connect(database_path) as connection:
        generation = connection.execute(
            """
            SELECT week_start, week_end, rotation_anchor
            FROM weekly_assignment_generations
            """
        ).fetchone()
        state = connection.execute(
            "SELECT first_week_start FROM assignment_rotation_state WHERE id = 1"
        ).fetchone()

    assert dict(generation) == {
        "week_start": "2026-11-16",
        "week_end": "2026-11-22",
        "rotation_anchor": "2026-11-16",
    }
    assert state["first_week_start"] == "2026-11-16"


def test_generation_advances_rotation_and_keeps_original_anchor(tmp_path):
    database_path = _database(tmp_path)

    first = generate_weekly_assignments(
        FIRST_WEEK,
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=GENERATED_ON,
    )
    second = generate_weekly_assignments(
        date(2026, 11, 23),
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=date(2026, 11, 23),
    )

    assert [item.chore_id for item in first] == [3, 1]
    assert [item.chore_id for item in second] == [1, 2]

    with connect(database_path) as connection:
        anchors = {
            row["rotation_anchor"]
            for row in connection.execute(
                "SELECT rotation_anchor FROM weekly_assignment_generations"
            )
        }
    assert anchors == {"2026-11-16"}


def test_repeated_generation_reuses_existing_assignments_and_snapshots(tmp_path):
    database_path = _database(tmp_path)

    first = generate_weekly_assignments(
        FIRST_WEEK,
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=GENERATED_ON,
    )
    with connect(database_path) as connection:
        connection.execute("UPDATE chores SET name = 'Renamed bathroom' WHERE id = 3")
        connection.execute(
            "UPDATE chore_checklist_items SET label = 'Changed label' WHERE id = 4"
        )
        connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Casey', 1)"
        )
        connection.execute(
            """
            INSERT INTO chores (name, description, is_active)
            VALUES ('Laundry', 'Wash clothes', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO chore_checklist_items (chore_id, label, position, is_active)
            VALUES (4, 'Wash clothes', 0, 1)
            """
        )

    repeated = generate_weekly_assignments(
        FIRST_WEEK,
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=date(2026, 11, 12),
    )

    assert repeated == first
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM assignment_checklist_items"
            ).fetchone()[0]
            == 3
        )


def test_generation_failure_rolls_back_rotation_state_and_all_assignments(tmp_path):
    database_path = _database(tmp_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_assignment_snapshot
            BEFORE INSERT ON assignment_checklist_items
            BEGIN
                SELECT RAISE(ABORT, 'injected snapshot failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected snapshot failure"):
        generate_weekly_assignments(
            FIRST_WEEK,
            database_path=database_path,
            timezone_name="America/Denver",
            generated_on=GENERATED_ON,
        )

    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM assignment_rotation_state"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM weekly_assignment_generations"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM assignment_checklist_items"
            ).fetchone()[0]
            == 0
        )


def test_catalog_changes_only_affect_later_week_and_preserve_history(tmp_path):
    database_path = _database(tmp_path)

    first = generate_weekly_assignments(
        FIRST_WEEK,
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=GENERATED_ON,
    )
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (?, '2026-11-16', 1, '2026-11-16T18:00:00Z')
            """,
            (first[0].checklist_items[0].id,),
        )
        connection.execute("UPDATE chores SET name = 'Renamed kitchen' WHERE id = 1")
        connection.execute(
            "UPDATE chore_checklist_items SET label = 'New floor task' WHERE id = 1"
        )

    second = generate_weekly_assignments(
        date(2026, 11, 23),
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=date(2026, 11, 23),
    )

    with connect(database_path) as connection:
        original = connection.execute(
            """
            SELECT chore_name_snapshot
            FROM weekly_assignments
            WHERE week_start = ? AND family_member_id = 2
            """,
            (FIRST_WEEK.isoformat(),),
        ).fetchone()
        original_item = connection.execute(
            """
            SELECT label_snapshot
            FROM assignment_checklist_items AS snapshot
            JOIN weekly_assignments AS assignment
              ON assignment.id = snapshot.weekly_assignment_id
            WHERE assignment.week_start = ? AND assignment.family_member_id = 2
            """,
            (FIRST_WEEK.isoformat(),),
        ).fetchone()
        later = connection.execute(
            """
            SELECT chore_name_snapshot
            FROM weekly_assignments
            WHERE week_start = ? AND family_member_id = 2
            """,
            (date(2026, 11, 23).isoformat(),),
        ).fetchone()
        completion = connection.execute(
            """
            SELECT completion_date, is_completed, completed_at
            FROM daily_checklist_completions
            WHERE assignment_checklist_item_id = ?
            """,
            (first[0].checklist_items[0].id,),
        ).fetchone()

    assert first[0].chore_name == "Bathroom"
    assert original["chore_name_snapshot"] == "Bathroom"
    assert original_item["label_snapshot"] == "Clean sink"
    assert later["chore_name_snapshot"] == "Renamed kitchen"
    assert second[0].chore_name == "Renamed kitchen"
    assert dict(completion) == {
        "completion_date": "2026-11-16",
        "is_completed": 1,
        "completed_at": "2026-11-16T18:00:00Z",
    }


def test_fewer_active_chores_rolls_back_generation_state(tmp_path):
    database_path = _database(tmp_path)
    with connect(database_path) as connection:
        connection.execute("UPDATE chores SET is_active = 0 WHERE id IN (2, 3)")

    with pytest.raises(ValueError, match="require at least"):
        generate_weekly_assignments(
            FIRST_WEEK,
            database_path=database_path,
            timezone_name="America/Denver",
            generated_on=GENERATED_ON,
        )

    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM assignment_rotation_state"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM weekly_assignment_generations"
            ).fetchone()[0]
            == 0
        )


def test_week_normalization_uses_configured_timezone_for_aware_datetime(tmp_path):
    database_path = _database(tmp_path)

    assignments = generate_weekly_assignments(
        # Monday UTC is still Sunday in Denver and belongs to the prior week.
        datetime.fromisoformat("2026-11-23T01:00:00+00:00"),
        database_path=database_path,
        timezone_name="America/Denver",
        generated_on=GENERATED_ON,
    )

    assert assignments[0].week_start == FIRST_WEEK
    assert assignments[0].week_end == date(2026, 11, 22)
