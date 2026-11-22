"""Integration tests for the durable weekly rollover scheduler."""

from __future__ import annotations

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config

from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.weekly_assignments import (
    SQLiteWeeklyAssignmentPersistence,
)
from chore_tracker.adapters.sqlite.weekly_reports import SQLiteWeeklyReportPersistence
from chore_tracker.adapters.sqlite.weekly_rollover import (
    SQLiteWeeklyRolloverPersistence,
)
from chore_tracker.application.services.weekly_assignment_generation import (
    WeeklyAssignmentGenerationService,
)
from chore_tracker.application.services.weekly_reports import (
    DailyStatus,
    WeeklyReportService,
)
from chore_tracker.application.services.weekly_rollover import (
    WeeklyRolloverResult,
    WeeklyRolloverService,
    latest_due_week_start,
    next_run_at,
)

ROOT = Path(__file__).resolve().parents[1]
TIMEZONE = "America/Denver"
ZONE = ZoneInfo(TIMEZONE)
WEEK_START = date(2026, 11, 23)
REPORT_WEEK_START = WEEK_START - timedelta(days=7)
RUN_AT = datetime(2026, 11, 23, 3, 0, tzinfo=ZONE)
RUN_AT_UTC = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
DEFAULT_MEMBERS = ("Alex", "Sam")
DEFAULT_CHORES = (
    ("Kitchen", "Clean the kitchen", ("Sweep floor", "Wipe counters")),
    ("Bathroom", "Clean the bathroom", ("Clean sink",)),
    ("Laundry", "Wash the clothes", ("Sort laundry",)),
)


def _database(tmp_path: Path) -> Path:
    database_path = tmp_path / "rollover.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")
    return database_path


def _seed_catalog(database_path: Path) -> dict[str, int]:
    member_ids = {}
    with connect(database_path) as connection:
        for member in DEFAULT_MEMBERS:
            member_ids[member] = connection.execute(
                """
                INSERT INTO family_members (display_name, is_active)
                VALUES (?, 1)
                """,
                (member,),
            ).lastrowid
        for name, description, checklist_items in DEFAULT_CHORES:
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


def _assignment_service(database_path: Path) -> WeeklyAssignmentGenerationService:
    return WeeklyAssignmentGenerationService(
        SQLiteWeeklyAssignmentPersistence(database_path), TIMEZONE
    )


def _report_service(database_path: Path) -> WeeklyReportService:
    return WeeklyReportService(SQLiteWeeklyReportPersistence(database_path), TIMEZONE)


def _rollover_service(database_path: Path) -> WeeklyRolloverService:
    return WeeklyRolloverService(
        reports=_report_service(database_path),
        assignments=_assignment_service(database_path),
        persistence=SQLiteWeeklyRolloverPersistence(database_path),
        timezone_name=TIMEZONE,
        delivery_time=time(3, 0),
    )


def _generate_assignments(
    database_path: Path, week_start: date, *, generated_on: date | None = None
):
    return _assignment_service(database_path).generate(
        week_start, generated_on=generated_on or week_start
    )


def _set_completion(
    database_path: Path, item_id: int, day: date, *, is_completed: bool = True
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


def _complete_day(database_path: Path, assignment, day: date) -> None:
    for item in assignment.checklist_items:
        _set_completion(database_path, item.id, day)


def _complete_week(database_path: Path, assignment, week_start: date) -> None:
    for day_index in range(7):
        _complete_day(database_path, assignment, week_start + timedelta(days=day_index))


def _prepared_week(tmp_path: Path):
    database_path = _database(tmp_path)
    member_ids = _seed_catalog(database_path)
    assignments = _generate_assignments(database_path, REPORT_WEEK_START)
    by_member = {assignment.family_member_id: assignment for assignment in assignments}
    _complete_week(database_path, by_member[member_ids["Alex"]], REPORT_WEEK_START)
    for day_index in range(3):
        _complete_day(
            database_path,
            by_member[member_ids["Sam"]],
            REPORT_WEEK_START + timedelta(days=day_index),
        )
    return database_path, member_ids, assignments


def _count(database_path: Path, table: str, where: str = "") -> int:
    query = f"SELECT COUNT(*) FROM {table}"
    if where:
        query += f" WHERE {where}"
    with connect(database_path) as connection:
        return connection.execute(query).fetchone()[0]


def test_checkpoint_starts_empty_and_advances_forward(tmp_path) -> None:
    database_path = _database(tmp_path)
    persistence = SQLiteWeeklyRolloverPersistence(database_path)

    assert persistence.last_completed_week_start() is None

    persistence.mark_completed(WEEK_START, RUN_AT_UTC)
    assert persistence.last_completed_week_start() == WEEK_START

    persistence.mark_completed(WEEK_START + timedelta(days=7), RUN_AT_UTC)
    assert persistence.last_completed_week_start() == WEEK_START + timedelta(days=7)


def test_checkpoint_does_not_regress_or_rewrite_the_completed_week(tmp_path) -> None:
    database_path = _database(tmp_path)
    persistence = SQLiteWeeklyRolloverPersistence(database_path)
    persistence.mark_completed(WEEK_START, RUN_AT_UTC)

    persistence.mark_completed(WEEK_START - timedelta(days=7), RUN_AT_UTC)
    persistence.mark_completed(WEEK_START, RUN_AT_UTC + timedelta(hours=1))

    assert persistence.last_completed_week_start() == WEEK_START
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT completed_at
            FROM weekly_rollover_state
            WHERE id = 1
            """
        ).fetchone()
    assert row["completed_at"] == "2026-11-23T10:00:00.000Z"


def test_checkpoint_rejects_invalid_week_and_timestamp(tmp_path) -> None:
    database_path = _database(tmp_path)
    persistence = SQLiteWeeklyRolloverPersistence(database_path)

    with pytest.raises(ValueError, match="Monday"):
        persistence.mark_completed(WEEK_START + timedelta(days=1), RUN_AT_UTC)
    with pytest.raises(ValueError, match="timezone-aware"):
        persistence.mark_completed(WEEK_START, datetime(2026, 11, 23, 10, 0))
    with pytest.raises(TypeError, match="week_start must be a date"):
        persistence.mark_completed(datetime(2026, 11, 23, 10, 0), RUN_AT_UTC)
    with pytest.raises(TypeError, match="completed_at"):
        persistence.mark_completed(WEEK_START, "2026-11-23T10:00:00Z")


def test_first_run_persists_prior_report_before_current_assignments(
    tmp_path, monkeypatch
) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    report_service = _report_service(database_path)
    assignment_persistence = SQLiteWeeklyAssignmentPersistence(database_path)
    original_generate = assignment_persistence.generate
    reports_seen_before_generation = []

    def checked_generate(*args, **kwargs):
        report = report_service.get_report(REPORT_WEEK_START)
        assert report is not None
        reports_seen_before_generation.append(report.id)
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(assignment_persistence, "generate", checked_generate)
    service = WeeklyRolloverService(
        reports=report_service,
        assignments=WeeklyAssignmentGenerationService(assignment_persistence, TIMEZONE),
        persistence=SQLiteWeeklyRolloverPersistence(database_path),
        timezone_name=TIMEZONE,
        delivery_time=time(3, 0),
    )

    results = service.run_due(RUN_AT)

    assert len(results) == 1
    result = results[0]
    report = report_service.get_report(REPORT_WEEK_START)
    assert report is not None
    assert result == WeeklyRolloverResult(
        assignment_week_start=WEEK_START,
        report_week_start=REPORT_WEEK_START,
        report_id=report.id,
        assignment_count=2,
    )
    assert reports_seen_before_generation == [report.id]
    assert report.week_start == REPORT_WEEK_START
    assert report.generated_at == RUN_AT_UTC
    assert report.summary.family_member_count == 2
    assert report.summary.total_days == 14
    assert report.summary.completed_days == 10
    assert report.summary.incomplete_days == 4
    assert [entry.family_member_name for entry in report.entries] == ["Alex", "Sam"]
    assert report.entries[0].completed_days == 7
    assert report.entries[1].completed_days == 3
    assert report.entries[1].days[3].status is DailyStatus.INCOMPLETE
    headers = report_service.list_reports()
    assert len(headers) == 1
    assert headers[0].id == report.id
    assert headers[0].week_start == REPORT_WEEK_START
    assert headers[0].summary == report.summary

    current = _assignment_service(database_path).generate(WEEK_START)
    assert len(current) == 2
    assert {assignment.week_start for assignment in current} == {WEEK_START}
    assert {assignment.chore_name for assignment in current} == {"Kitchen", "Laundry"}
    assert _count(database_path, "weekly_assignments", "week_start = '2026-11-23'") == 2
    assert _count(database_path, "weekly_report_entries") == 2
    assert _count(database_path, "weekly_report_days") == 14
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        == WEEK_START
    )


def test_repeated_run_is_a_no_op_and_preserves_the_report(tmp_path) -> None:
    database_path, member_ids, _ = _prepared_week(tmp_path)
    service = _rollover_service(database_path)
    first_results = service.run_due(RUN_AT)
    first_report = _report_service(database_path).get_report(REPORT_WEEK_START)

    with connect(database_path) as connection:
        connection.execute(
            "UPDATE family_members SET display_name = 'Renamed' WHERE id = ?",
            (member_ids["Alex"],),
        )
        connection.execute("DELETE FROM daily_checklist_completions")

    repeated_results = service.run_due(RUN_AT + timedelta(hours=1))

    assert len(first_results) == 1
    assert repeated_results == ()
    assert _report_service(database_path).get_report(REPORT_WEEK_START) == first_report
    assert _count(database_path, "weekly_reports") == 1
    assert _count(database_path, "weekly_report_entries") == 2
    assert _count(database_path, "weekly_report_days") == 14
    assert _count(database_path, "weekly_assignments") == 4
    assert _count(database_path, "weekly_assignment_generations") == 2


def test_overlapping_runs_do_not_duplicate_reports_or_assignments(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)

    def run_once(_: int):
        return _rollover_service(database_path).run_due(RUN_AT)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run_once, range(2)))

    report_ids = {result.report_id for batch in results for result in batch}
    assert len(report_ids) == 1
    assert _count(database_path, "weekly_reports") == 1
    assert _count(database_path, "weekly_report_entries") == 2
    assert _count(database_path, "weekly_report_days") == 14
    assert _count(database_path, "weekly_assignments") == 4
    assert _count(database_path, "weekly_assignment_generations") == 2
    assert _count(database_path, "weekly_rollover_state") == 1


def test_missed_mondays_are_recovered_in_order_without_duplication(tmp_path) -> None:
    database_path = _database(tmp_path)
    _seed_catalog(database_path)
    missed_from = WEEK_START - timedelta(days=14)
    _generate_assignments(database_path, missed_from)
    _generate_assignments(database_path, missed_from + timedelta(days=7))
    SQLiteWeeklyRolloverPersistence(database_path).mark_completed(
        missed_from, RUN_AT_UTC - timedelta(days=14)
    )
    service = _rollover_service(database_path)

    results = service.run_due(RUN_AT)

    assert [result.assignment_week_start for result in results] == [
        WEEK_START - timedelta(days=7),
        WEEK_START,
    ]
    assert [result.report_week_start for result in results] == [
        missed_from,
        WEEK_START - timedelta(days=7),
    ]
    report_service = _report_service(database_path)
    assert [report.week_start for report in report_service.list_reports()] == [
        WEEK_START - timedelta(days=7),
        missed_from,
    ]
    assert _count(database_path, "weekly_assignments") == 6
    assert _count(database_path, "weekly_assignment_generations") == 3
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        == WEEK_START
    )

    assert service.run_due(RUN_AT + timedelta(hours=1)) == ()
    assert _count(database_path, "weekly_reports") == 2


def test_report_failure_leaves_no_partial_report_and_can_be_retried(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    service = _rollover_service(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_weekly_report_entry
            BEFORE INSERT ON weekly_report_entries
            BEGIN
                SELECT RAISE(ABORT, 'injected report failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected report failure"):
        service.run_due(RUN_AT)

    assert _count(database_path, "weekly_reports") == 0
    assert _count(database_path, "weekly_report_entries") == 0
    assert _count(database_path, "weekly_report_days") == 0
    assert _count(database_path, "weekly_assignments", "week_start = '2026-11-23'") == 0
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        is None
    )

    with connect(database_path) as connection:
        connection.execute("DROP TRIGGER fail_weekly_report_entry")

    results = service.run_due(RUN_AT)
    assert len(results) == 1
    assert _count(database_path, "weekly_reports") == 1
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        == WEEK_START
    )


def test_assignment_failure_keeps_finalized_report_for_retry(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    service = _rollover_service(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_weekly_assignment
            BEFORE INSERT ON weekly_assignments
            BEGIN
                SELECT RAISE(ABORT, 'injected assignment failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected assignment failure"):
        service.run_due(RUN_AT)

    report = _report_service(database_path).get_report(REPORT_WEEK_START)
    assert report is not None
    assert report.summary.completed_days == 10
    assert _count(database_path, "weekly_assignments", "week_start = '2026-11-23'") == 0
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        is None
    )

    with connect(database_path) as connection:
        connection.execute("DROP TRIGGER fail_weekly_assignment")

    results = service.run_due(RUN_AT)
    assert len(results) == 1
    assert results[0].report_id == report.id
    assert _count(database_path, "weekly_reports") == 1
    assert _count(database_path, "weekly_assignments", "week_start = '2026-11-23'") == 2
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        == WEEK_START
    )


def test_checkpoint_failure_retries_without_duplication(tmp_path) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    service = _rollover_service(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_rollover_checkpoint
            BEFORE INSERT ON weekly_rollover_state
            BEGIN
                SELECT RAISE(ABORT, 'injected checkpoint failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected checkpoint failure"):
        service.run_due(RUN_AT)

    report = _report_service(database_path).get_report(REPORT_WEEK_START)
    assert report is not None
    assert _count(database_path, "weekly_assignments", "week_start = '2026-11-23'") == 2
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        is None
    )

    with connect(database_path) as connection:
        connection.execute("DROP TRIGGER fail_rollover_checkpoint")

    results = service.run_due(RUN_AT)
    assert len(results) == 1
    assert results[0].report_id == report.id
    assert _count(database_path, "weekly_reports") == 1
    assert _count(database_path, "weekly_assignments", "week_start = '2026-11-23'") == 2
    assert (
        SQLiteWeeklyRolloverPersistence(database_path).last_completed_week_start()
        == WEEK_START
    )


def test_rollover_logs_week_context_and_outcome_without_names(tmp_path, caplog) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    caplog.set_level(
        logging.INFO, logger="chore_tracker.application.services.weekly_rollover"
    )

    _rollover_service(database_path).run_due(RUN_AT)

    assert "reporting_week=2026-11-16" in caplog.text
    assert "assignment_week=2026-11-23" in caplog.text
    assert "outcome=completed" in caplog.text
    assert "Alex" not in caplog.text
    assert "Sam" not in caplog.text


def test_failed_rollover_logs_week_context_without_names(tmp_path, caplog) -> None:
    database_path, _, _ = _prepared_week(tmp_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_weekly_report_entry
            BEFORE INSERT ON weekly_report_entries
            BEGIN
                SELECT RAISE(ABORT, 'injected report failure');
            END
            """
        )
    caplog.set_level(
        logging.INFO, logger="chore_tracker.application.services.weekly_rollover"
    )

    with pytest.raises(sqlite3.IntegrityError, match="injected report failure"):
        _rollover_service(database_path).run_due(RUN_AT)

    assert "reporting_week=2026-11-16" in caplog.text
    assert "assignment_week=2026-11-23" in caplog.text
    assert "outcome=failed" in caplog.text
    assert "Alex" not in caplog.text
    assert "Sam" not in caplog.text


def test_latest_due_week_uses_configured_delivery_time() -> None:
    delivery_time = time(3, 0)

    assert (
        latest_due_week_start(
            datetime(2026, 11, 23, 2, 59, tzinfo=ZONE), delivery_time, ZONE
        )
        == REPORT_WEEK_START
    )
    assert (
        latest_due_week_start(
            datetime(2026, 11, 23, 3, 0, tzinfo=ZONE), delivery_time, ZONE
        )
        == WEEK_START
    )
    assert (
        latest_due_week_start(
            datetime(2026, 11, 22, 23, 0, tzinfo=ZONE), delivery_time, ZONE
        )
        == REPORT_WEEK_START
    )


def test_next_run_is_monday_in_configured_timezone() -> None:
    delivery_time = time(3, 0)
    next_monday = datetime(2026, 11, 30, 3, 0, tzinfo=ZONE)

    assert next_run_at(
        datetime(2026, 11, 22, 23, 0, tzinfo=ZONE), delivery_time, ZONE
    ) == datetime(2026, 11, 23, 3, 0, tzinfo=ZONE)
    assert next_run_at(
        datetime(2026, 11, 23, 2, 59, tzinfo=ZONE), delivery_time, ZONE
    ) == datetime(2026, 11, 23, 3, 0, tzinfo=ZONE)
    assert (
        next_run_at(datetime(2026, 11, 23, 3, 0, tzinfo=ZONE), delivery_time, ZONE)
        == next_monday
    )
    assert (
        next_run_at(datetime(2026, 11, 23, 4, 0, tzinfo=ZONE), delivery_time, ZONE)
        == next_monday
    )
    assert (
        next_run_at(datetime(2026, 11, 23, 10, 0, tzinfo=UTC), delivery_time, ZONE)
        == next_monday
    )
