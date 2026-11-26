"""Integration tests for immutable weekly completion reports."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.weekly_assignments import (
    SQLiteWeeklyAssignmentPersistence,
)
from chore_tracker.adapters.sqlite.weekly_reports import SQLiteWeeklyReportPersistence
from chore_tracker.application.services.weekly_assignment_generation import (
    generate_weekly_assignments as _generate_weekly_assignments,
)
from chore_tracker.application.services.weekly_reports import (
    DailyStatus,
    WeeklyReportReward,
    WeeklyReportService,
    WeeklyReportSummary,
)

ROOT = Path(__file__).resolve().parents[1]
WEEK_START = date(2026, 11, 16)
WEEK_END = date(2026, 11, 22)
GENERATED_AT = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)
DEFAULT_MEMBERS = ("Alex", "Sam")
DEFAULT_CHORES = (
    ("Kitchen", "Clean the kitchen", ("Sweep floor", "Wipe counters")),
    ("Bathroom", "Clean the bathroom", ("Clean sink",)),
    ("Laundry", "Wash the clothes", ("Sort laundry",)),
)


def _database(tmp_path: Path) -> Path:
    database_path = tmp_path / "reports.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")
    return database_path


def _seed_catalog(
    database_path: Path,
    *,
    members: tuple[str, ...] = DEFAULT_MEMBERS,
    chores: tuple[tuple[str, str, tuple[str, ...]], ...] = DEFAULT_CHORES,
) -> dict[str, int]:
    member_ids = {}
    with connect(database_path) as connection:
        for member in members:
            member_ids[member] = connection.execute(
                """
                INSERT INTO family_members (display_name, is_active)
                VALUES (?, 1)
                """,
                (member,),
            ).lastrowid
        for name, description, checklist_items in chores:
            chore_id = connection.execute(
                """
                INSERT INTO chores (name, description, is_active)
                VALUES (?, ?, 1)
                """,
                (name, description),
            ).lastrowid
            connection.executemany(
                """
                INSERT INTO chore_checklist_items (
                    chore_id, label, position, is_active
                )
                VALUES (?, ?, ?, 1)
                """,
                [
                    (chore_id, label, position)
                    for position, label in enumerate(checklist_items)
                ],
            )
    return member_ids


def _generate_assignments(
    database_path: Path,
    week_start: date = WEEK_START,
    *,
    generated_on: date = date(2026, 11, 11),
):
    return _generate_weekly_assignments(
        week_start,
        persistence=SQLiteWeeklyAssignmentPersistence(database_path),
        timezone_name="America/Denver",
        generated_on=generated_on,
    )


def _prepared_week(
    tmp_path: Path,
    *,
    members: tuple[str, ...] = DEFAULT_MEMBERS,
    chores: tuple[tuple[str, str, tuple[str, ...]], ...] = DEFAULT_CHORES,
):
    database_path = _database(tmp_path)
    member_ids = _seed_catalog(database_path, members=members, chores=chores)
    assignments = _generate_assignments(database_path)
    return database_path, member_ids, assignments


def _service(database_path: Path) -> WeeklyReportService:
    return WeeklyReportService(
        SQLiteWeeklyReportPersistence(database_path), "America/Denver"
    )


def _set_completion(
    database_path: Path,
    item_id: int,
    day: date,
    *,
    is_completed: bool = True,
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT (assignment_checklist_item_id, completion_date)
            DO UPDATE SET is_completed = excluded.is_completed,
                          completed_at = excluded.completed_at
            """,
            (
                item_id,
                day.isoformat(),
                int(is_completed),
                f"{day.isoformat()}T18:00:00Z" if is_completed else None,
            ),
        )


def _complete_assignment_day(
    database_path: Path,
    assignment,
    day: date,
    *,
    item_indexes: tuple[int, ...] | None = None,
) -> None:
    items = assignment.checklist_items
    selected = (
        items if item_indexes is None else tuple(items[index] for index in item_indexes)
    )
    for item in selected:
        _set_completion(database_path, item.id, day)


def _complete_assignment_week(
    database_path: Path, assignment, week_start: date = WEEK_START
) -> None:
    for day_index in range(7):
        _complete_assignment_day(
            database_path, assignment, week_start + timedelta(days=day_index)
        )


def _statuses_from_records(
    database_path: Path, assignment, week_start: date = WEEK_START
) -> tuple[DailyStatus, ...]:
    with connect(database_path) as connection:
        item_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM assignment_checklist_items
            WHERE weekly_assignment_id = ?
            """,
            (assignment.id,),
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT completion.completion_date,
                   SUM(completion.is_completed) AS completed_count
            FROM assignment_checklist_items AS item
            JOIN daily_checklist_completions AS completion
              ON completion.assignment_checklist_item_id = item.id
            WHERE item.weekly_assignment_id = ?
            GROUP BY completion.completion_date
            """,
            (assignment.id,),
        ).fetchall()
    completed_counts = {row["completion_date"]: row["completed_count"] for row in rows}
    return tuple(
        (
            DailyStatus.COMPLETE
            if item_count > 0 and completed_counts.get(day.isoformat(), 0) == item_count
            else DailyStatus.INCOMPLETE
        )
        for day in (week_start + timedelta(days=index) for index in range(7))
    )


def _entry(report, family_member_name: str):
    return next(
        entry
        for entry in report.entries
        if entry.family_member_name == family_member_name
    )


def test_generates_all_complete_report_for_normalized_week(tmp_path) -> None:
    database_path, member_ids, assignments = _prepared_week(tmp_path)
    for assignment in assignments:
        _complete_assignment_week(database_path, assignment)

    report = _service(database_path).generate(
        date(2026, 11, 18), generated_at=GENERATED_AT
    )

    assert report.week_start == WEEK_START
    assert report.week_end == WEEK_END
    assert report.generated_at == GENERATED_AT
    assert report.summary == WeeklyReportSummary(
        family_member_count=2,
        total_days=14,
        completed_days=14,
        incomplete_days=0,
    )
    assert [entry.family_member_name for entry in report.entries] == ["Alex", "Sam"]
    assert {entry.family_member_id for entry in report.entries} == set(
        member_ids.values()
    )
    for entry in report.entries:
        assert entry.completed_days == 7
        assert entry.incomplete_days == 0
        assert [day.report_date for day in entry.days] == [
            WEEK_START + timedelta(days=index) for index in range(7)
        ]
        assert all(day.status is DailyStatus.COMPLETE for day in entry.days)

    assert _service(database_path).get_report(WEEK_START) == report
    assert _service(database_path).get_report(WEEK_END) == report


def test_partial_completions_drive_statuses_and_totals(tmp_path) -> None:
    database_path, member_ids, assignments = _prepared_week(tmp_path)
    alex_assignment = next(
        item for item in assignments if item.family_member_id == member_ids["Alex"]
    )
    sam_assignment = next(
        item for item in assignments if item.family_member_id == member_ids["Sam"]
    )
    assert len(sam_assignment.checklist_items) == 2

    _complete_assignment_week(database_path, alex_assignment)
    for day_index in range(3):
        _complete_assignment_day(
            database_path, sam_assignment, WEEK_START + timedelta(days=day_index)
        )
    _complete_assignment_day(
        database_path,
        sam_assignment,
        WEEK_START + timedelta(days=3),
        item_indexes=(0,),
    )

    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)

    alex_entry = _entry(report, "Alex")
    sam_entry = _entry(report, "Sam")
    assert alex_entry.completed_days == 7
    assert alex_entry.incomplete_days == 0
    assert sam_entry.completed_days == 3
    assert sam_entry.incomplete_days == 4
    assert [day.status for day in sam_entry.days] == [
        DailyStatus.COMPLETE,
        DailyStatus.COMPLETE,
        DailyStatus.COMPLETE,
        DailyStatus.INCOMPLETE,
        DailyStatus.INCOMPLETE,
        DailyStatus.INCOMPLETE,
        DailyStatus.INCOMPLETE,
    ]
    assert report.summary == WeeklyReportSummary(
        family_member_count=2,
        total_days=14,
        completed_days=10,
        incomplete_days=4,
    )

    for entry, assignment in (
        (alex_entry, alex_assignment),
        (sam_entry, sam_assignment),
    ):
        assert tuple(day.status for day in entry.days) == _statuses_from_records(
            database_path, assignment
        )
    assert (
        sum(
            day.status is DailyStatus.COMPLETE
            for entry in report.entries
            for day in entry.days
        )
        == report.summary.completed_days
    )


def test_week_with_no_completion_records_is_reported_as_incomplete(tmp_path) -> None:
    database_path, _, assignments = _prepared_week(tmp_path)

    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)

    assert report.summary == WeeklyReportSummary(
        family_member_count=2,
        total_days=14,
        completed_days=0,
        incomplete_days=14,
    )
    assert len(report.entries) == len(assignments)
    for entry in report.entries:
        assert entry.completed_days == 0
        assert entry.incomplete_days == 7
        assert all(day.status is DailyStatus.INCOMPLETE for day in entry.days)


def test_report_includes_inactive_assigned_child_but_not_unassigned_child(
    tmp_path,
) -> None:
    database_path, member_ids, _ = _prepared_week(tmp_path)
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE family_members SET is_active = 0 WHERE id = ?",
            (member_ids["Alex"],),
        )
        connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Riley', 1)"
        )

    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)

    assert [entry.family_member_name for entry in report.entries] == ["Alex", "Sam"]
    assert report.summary.family_member_count == 2
    assert _entry(report, "Alex").family_member_id == member_ids["Alex"]


def test_report_covers_exact_week_and_ignores_adjacent_weeks(tmp_path) -> None:
    database_path = _database(tmp_path)
    _seed_catalog(database_path)
    previous_start = WEEK_START - timedelta(days=7)
    previous_assignments = _generate_assignments(
        database_path, previous_start, generated_on=date(2026, 11, 4)
    )
    assignments = _generate_assignments(
        database_path, WEEK_START, generated_on=date(2026, 11, 4)
    )
    for assignment in previous_assignments:
        _complete_assignment_week(database_path, assignment, previous_start)
    for assignment in assignments:
        _complete_assignment_week(database_path, assignment)

    service = _service(database_path)
    report = service.generate(WEEK_START, generated_at=GENERATED_AT)

    assert report.week_start == WEEK_START
    assert report.week_end == WEEK_END
    assert {entry.weekly_assignment_id for entry in report.entries} == {
        assignment.id for assignment in assignments
    }
    assert {day.report_date for entry in report.entries for day in entry.days} == {
        WEEK_START + timedelta(days=index) for index in range(7)
    }
    assert report.summary == WeeklyReportSummary(
        family_member_count=2,
        total_days=14,
        completed_days=14,
        incomplete_days=0,
    )
    assert service.generate(WEEK_END) == report

    # Monday 01:00 UTC is still Sunday in the configured reporting timezone.
    previous_report = service.generate(
        datetime(2026, 11, 16, 1, 0, tzinfo=UTC),
        generated_at=GENERATED_AT,
    )
    assert previous_report.week_start == previous_start
    assert {entry.weekly_assignment_id for entry in previous_report.entries} == {
        assignment.id for assignment in previous_assignments
    }


def test_persisted_report_is_unchanged_after_source_data_changes(tmp_path) -> None:
    database_path, member_ids, assignments = _prepared_week(tmp_path)
    _complete_assignment_week(database_path, assignments[0])
    first = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)

    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE family_members
            SET display_name = 'Alex Renamed', is_active = 0
            WHERE id = ?
            """,
            (member_ids["Alex"],),
        )
        connection.execute(
            """
            UPDATE chores
            SET name = 'Renamed chore', description = 'Changed description',
                is_active = 0
            """
        )
        connection.execute("UPDATE chore_checklist_items SET label = 'Changed label'")
        connection.execute("DELETE FROM chore_checklist_items")
        connection.execute(
            """
            INSERT INTO family_members (display_name, is_active)
            VALUES ('Riley', 1)
            """
        )
        connection.execute("DELETE FROM daily_checklist_completions")

    assert _service(database_path).get_report(WEEK_START) == first
    assert {entry.family_member_name for entry in first.entries} == {"Alex", "Sam"}
    assert first.entries[0].chore_name != "Renamed chore"


def test_repeated_generation_returns_the_first_snapshot(tmp_path) -> None:
    database_path, _, assignments = _prepared_week(tmp_path)
    first = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)
    assert first.summary.completed_days == 0

    for assignment in assignments:
        _complete_assignment_week(database_path, assignment)
    repeated = _service(database_path).generate(
        WEEK_START, generated_at=GENERATED_AT + timedelta(hours=1)
    )

    assert repeated == first
    assert repeated.id == first.id
    assert repeated.generated_at == GENERATED_AT
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0] == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_entries").fetchone()[
                0
            ]
            == 2
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_days").fetchone()[0]
            == 14
        )


def test_failed_generation_leaves_no_partial_report(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_weekly_report_day
            BEFORE INSERT ON weekly_report_days
            BEGIN
                SELECT RAISE(ABORT, 'injected report failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected report failure"):
        _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)

    with connect(database_path) as connection:
        for table in (
            "weekly_reports",
            "weekly_report_entries",
            "weekly_report_days",
        ):
            assert (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )
        connection.execute("DROP TRIGGER fail_weekly_report_day")

    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)
    assert report.summary.incomplete_days == 14


def test_report_entries_are_paginated_independently(tmp_path) -> None:
    database_path, _, _ = _prepared_week(
        tmp_path,
        members=("Alex", "Riley", "Sam"),
    )
    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)
    service = _service(database_path)

    first_page = service.get_report_entries(WEEK_START, limit=2)
    assert first_page is not None
    assert first_page.report_id == report.id
    assert first_page.total == 3
    assert first_page.offset == 0
    assert first_page.entries == report.entries[:2]

    second_page = service.get_report_entries(WEEK_START, limit=2, offset=2)
    assert second_page is not None
    assert second_page.total == 3
    assert second_page.offset == 2
    assert second_page.entries == report.entries[2:]

    empty_page = service.get_report_entries(WEEK_START, limit=2, offset=4)
    assert empty_page is not None
    assert empty_page.entries == ()

    assert service.get_report_entries(WEEK_START - timedelta(days=7)) is None
    for limit, offset in ((0, 0), (101, 0), (25, -1)):
        with pytest.raises(ValueError):
            service.get_report_entries(WEEK_START, limit=limit, offset=offset)


def test_persisted_report_rows_are_immutable_at_database_level(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)
    entry = report.entries[0]

    with connect(database_path) as connection:
        prohibited = (
            (
                "UPDATE weekly_reports SET completed_days = 0 WHERE id = ?",
                (report.id,),
            ),
            ("DELETE FROM weekly_reports WHERE id = ?", (report.id,)),
            (
                """
                UPDATE weekly_report_entries
                SET chore_name_snapshot = 'Changed'
                WHERE id = ?
                """,
                (entry.id,),
            ),
            ("DELETE FROM weekly_report_entries WHERE id = ?", (entry.id,)),
            (
                """
                UPDATE weekly_report_days
                SET status = 'incomplete'
                WHERE report_entry_id = ?
                """,
                (entry.id,),
            ),
            (
                "DELETE FROM weekly_report_days WHERE report_entry_id = ?",
                (entry.id,),
            ),
        )
        for statement, parameters in prohibited:
            try:
                connection.execute(statement, parameters)
            except sqlite3.IntegrityError as error:
                assert "immutable" in str(error) or "cannot be deleted" in str(error)
            else:
                raise AssertionError(
                    f"Prohibited report operation succeeded: {statement}"
                )

    assert _service(database_path).get_report(WEEK_START) == report


def test_lists_finalized_report_headers_newest_first(tmp_path) -> None:
    database_path = _database(tmp_path)
    _seed_catalog(database_path)
    previous_start = WEEK_START - timedelta(days=7)
    _generate_assignments(database_path, previous_start, generated_on=date(2026, 11, 4))
    _generate_assignments(database_path, WEEK_START, generated_on=date(2026, 11, 4))
    service = _service(database_path)
    older = service.generate(previous_start, generated_at=GENERATED_AT)
    newer = service.generate(WEEK_START, generated_at=GENERATED_AT)

    headers = service.list_reports()

    assert [header.week_start for header in headers] == [WEEK_START, previous_start]
    assert [header.id for header in headers] == [newer.id, older.id]
    assert headers[0].summary == newer.summary
    header = service.get_report_header(WEEK_START)
    assert header is not None
    assert header.id == newer.id
    assert header.week_end == WEEK_END
    assert header.summary.completed_days == 0
    assert service.get_report_header(WEEK_START - timedelta(days=14)) is None


def test_reports_complete_days_from_required_items_only(tmp_path) -> None:
    database_path = _database(tmp_path)
    member_ids = _seed_catalog(database_path)
    with connect(database_path) as connection:
        bathroom_item = connection.execute(
            """
            SELECT item.id FROM chore_checklist_items AS item
            JOIN chores AS chore ON chore.id = item.chore_id
            WHERE chore.name = 'Bathroom'
            """
        ).fetchone()["id"]
        kitchen_optional = connection.execute(
            """
            SELECT item.id FROM chore_checklist_items AS item
            JOIN chores AS chore ON chore.id = item.chore_id
            WHERE chore.name = 'Kitchen'
            ORDER BY item.position
            LIMIT 1
            """
        ).fetchone()["id"]
        connection.execute(
            "UPDATE chore_checklist_items SET is_required = 0 WHERE id IN (?, ?)",
            (bathroom_item, kitchen_optional),
        )

    assignments = _generate_assignments(database_path, WEEK_START)
    by_member = {assignment.family_member_id: assignment for assignment in assignments}
    alex_assignment = by_member[member_ids["Alex"]]
    sam_assignment = by_member[member_ids["Sam"]]
    assert all(not item.is_required for item in alex_assignment.checklist_items)
    sam_required = [item for item in sam_assignment.checklist_items if item.is_required]
    sam_optional = [
        item for item in sam_assignment.checklist_items if not item.is_required
    ]
    assert len(sam_required) == 1
    assert len(sam_optional) == 1

    # Alex has only optional items, so every day is complete without records.
    # Sam needs the required item; checking only the optional item is incomplete.
    for day_index in range(7):
        day = WEEK_START + timedelta(days=day_index)
        if day_index != 1:
            for item in sam_required:
                _set_completion(database_path, item.id, day)
        if day_index == 1:
            for item in sam_optional:
                _set_completion(database_path, item.id, day)

    report = _service(database_path).generate(WEEK_START, generated_at=GENERATED_AT)

    alex_entry = _entry(report, "Alex")
    sam_entry = _entry(report, "Sam")
    assert alex_entry.completed_days == 7
    assert alex_entry.incomplete_days == 0
    assert sam_entry.completed_days == 6
    assert sam_entry.incomplete_days == 1
    assert sam_entry.days[1].status is DailyStatus.INCOMPLETE
    assert all(
        day.status is DailyStatus.COMPLETE
        for index, day in enumerate(sam_entry.days)
        if index != 1
    )
    assert report.summary == WeeklyReportSummary(
        family_member_count=2,
        total_days=14,
        completed_days=13,
        incomplete_days=1,
    )


def _add_administrator(database_path: Path, email: str = "admin@example.test") -> int:
    with connect(database_path) as connection:
        administrator_id = connection.execute(
            "INSERT INTO administrators (email) VALUES (?)", (email,)
        ).lastrowid
    return administrator_id


def test_marking_a_reward_records_audit_details_and_is_idempotent(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    service = _service(database_path)
    report = service.generate(WEEK_START, generated_at=GENERATED_AT)
    alex_entry = _entry(report, "Alex")
    administrator_id = _add_administrator(database_path)
    second_administrator_id = _add_administrator(
        database_path, "other-admin@example.test"
    )

    # A date in the middle of the week normalizes to the reporting week.
    reward = service.mark_entry_rewarded(
        date(2026, 11, 18),
        alex_entry.id,
        administrator_id,
        rewarded_at=GENERATED_AT,
    )

    assert reward == WeeklyReportReward(
        rewarded_at=GENERATED_AT,
        administrator_id=administrator_id,
        administrator_email="admin@example.test",
    )
    page = service.get_report_entries(WEEK_START)
    assert page is not None
    page_rewards = {entry.family_member_name: entry.reward for entry in page.entries}
    assert page_rewards["Alex"] == reward
    assert page_rewards["Sam"] is None
    full_report = service.get_report(WEEK_START)
    assert full_report is not None
    assert _entry(full_report, "Alex").reward == reward

    # A repeated marking request, even from another administrator, keeps the
    # first recorded audit action instead of creating a conflicting duplicate.
    repeated = service.mark_entry_rewarded(
        WEEK_START,
        alex_entry.id,
        second_administrator_id,
        rewarded_at=GENERATED_AT + timedelta(hours=1),
    )
    assert repeated == reward
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 1
        )


def test_marking_a_reward_for_an_unknown_entry_or_week_returns_none(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    service = _service(database_path)
    report = service.generate(WEEK_START, generated_at=GENERATED_AT)
    entry = _entry(report, "Alex")
    administrator_id = _add_administrator(database_path)

    assert (
        service.mark_entry_rewarded(
            WEEK_START, 999999, administrator_id, rewarded_at=GENERATED_AT
        )
        is None
    )
    assert (
        service.mark_entry_rewarded(
            WEEK_START + timedelta(days=7),
            entry.id,
            administrator_id,
            rewarded_at=GENERATED_AT,
        )
        is None
    )
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 0
        )


def test_marking_a_reward_requires_a_finalized_report(tmp_path) -> None:
    database_path, member_ids, _ = _prepared_week(tmp_path)
    service = _service(database_path)
    service.generate(WEEK_START, generated_at=GENERATED_AT)
    administrator_id = _add_administrator(database_path)
    next_week = WEEK_START + timedelta(days=7)

    with connect(database_path) as connection:
        chore_id = connection.execute(
            "SELECT id FROM chores WHERE name = 'Kitchen'"
        ).fetchone()["id"]
        assignment_id = connection.execute(
            """
            INSERT INTO weekly_assignments (
                family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot
            )
            VALUES (?, ?, ?, ?, 'Kitchen', 'Clean')
            """,
            (
                member_ids["Alex"],
                chore_id,
                next_week.isoformat(),
                (next_week + timedelta(days=6)).isoformat(),
            ),
        ).lastrowid
        report_id = connection.execute(
            """
            INSERT INTO weekly_reports (
                week_start, week_end, family_member_count, total_days,
                completed_days, incomplete_days, generated_at
            )
            VALUES (?, ?, 0, 0, 0, 0, '2026-11-30T10:00:00Z')
            """,
            (next_week.isoformat(), (next_week + timedelta(days=6)).isoformat()),
        ).lastrowid
        entry_id = connection.execute(
            """
            INSERT INTO weekly_report_entries (
                report_id, weekly_assignment_id, position, family_member_id,
                family_member_name_snapshot, chore_name_snapshot,
                chore_description_snapshot, completed_days, incomplete_days
            )
            VALUES (?, ?, 0, ?, 'Alex', 'Kitchen', 'Clean', 0, 7)
            """,
            (report_id, assignment_id, member_ids["Alex"]),
        ).lastrowid

    assert (
        service.mark_entry_rewarded(
            next_week, entry_id, administrator_id, rewarded_at=GENERATED_AT
        )
        is None
    )
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 0
        )
