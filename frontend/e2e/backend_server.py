"""Start a disposable, seeded backend for Playwright browser tests."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = ROOT / "frontend" / ".playwright-data"
DATABASE_PATH = DATA_DIRECTORY / "chore-tracker-e2e.db"
BACKEND_PORT = 8001
FRONTEND_ORIGIN = "http://localhost:5174"
REPORT_TIMEZONE = "America/Denver"
E2E_TODAY = date(2026, 11, 9)
test_today = E2E_TODAY


class TodayBody(BaseModel):
    date: date


class WeekBody(BaseModel):
    week_start: date


class RolloverBody(BaseModel):
    now: datetime


def configure_environment() -> None:
    """Set isolated configuration before the application settings are imported."""
    os.environ.update(
        {
            "CHORE_TRACKER_ENVIRONMENT": "test",
            "CHORE_TRACKER_APP_HOST": "127.0.0.1",
            "CHORE_TRACKER_APP_PORT": str(BACKEND_PORT),
            "CHORE_TRACKER_APP_ORIGIN": FRONTEND_ORIGIN,
            "CHORE_TRACKER_PASSKEY_ORIGIN": FRONTEND_ORIGIN,
            "CHORE_TRACKER_PASSKEY_RP_ID": "localhost",
            "CHORE_TRACKER_DATABASE_PATH": str(DATABASE_PATH),
            "CHORE_TRACKER_REPORT_TIMEZONE": REPORT_TIMEZONE,
            # The fixture owns deterministic reports, assignments, and rollover;
            # the live scheduler is never started during browser tests.
            "CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED": "false",
        }
    )


def reset_database() -> None:
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-shm", "-wal"):
        (DATA_DIRECTORY / f"{DATABASE_PATH.name}{suffix}").unlink(missing_ok=True)

    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(DATABASE_PATH)
    command.upgrade(config, "head")


def seed_database() -> None:
    """Create current and previous week assignments with varied history statuses."""
    week_start = E2E_TODAY - timedelta(days=E2E_TODAY.weekday())
    week_end = week_start + timedelta(days=6)
    prior_start = week_start - timedelta(days=7)
    prior_end = week_end - timedelta(days=7)
    older_start = week_start - timedelta(days=14)
    older_end = week_end - timedelta(days=14)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        member_ids = {}
        for display_name in (
            "Alex",
            "Sam",
            "Riley",
            "Avery",
            "Jordan",
            "Morgan",
            "Taylor",
        ):
            member_ids[display_name] = connection.execute(
                "INSERT INTO family_members (display_name) VALUES (?)",
                (display_name,),
            ).lastrowid

        def create_chore(name: str, description: str, labels: tuple[str, ...]):
            chore_id = connection.execute(
                """INSERT INTO chores (name, description, is_active)
                   VALUES (?, ?, 1)""",
                (name, description),
            ).lastrowid
            item_ids = []
            for position, label in enumerate(labels):
                item_ids.append(
                    connection.execute(
                        """INSERT INTO chore_checklist_items
                           (chore_id, label, position, is_active)
                           VALUES (?, ?, ?, 1)""",
                        (chore_id, label, position),
                    ).lastrowid
                )
            return chore_id, item_ids

        def assign(
            member_name: str,
            chore_id: int,
            item_ids: list[int],
            start,
            end,
            name: str,
            description: str,
        ):
            assignment_id = connection.execute(
                """INSERT INTO weekly_assignments
                   (family_member_id, chore_id, week_start, week_end,
                    chore_name_snapshot, chore_description_snapshot)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    member_ids[member_name],
                    chore_id,
                    start.isoformat(),
                    end.isoformat(),
                    name,
                    description,
                ),
            ).lastrowid
            snapshot_ids = []
            for position, item_id in enumerate(item_ids):
                label = connection.execute(
                    "SELECT label FROM chore_checklist_items WHERE id = ?",
                    (item_id,),
                ).fetchone()["label"]
                snapshot_ids.append(
                    connection.execute(
                        """INSERT INTO assignment_checklist_items
                           (weekly_assignment_id, source_checklist_item_id,
                            label_snapshot, position)
                           VALUES (?, ?, ?, ?)""",
                        (assignment_id, item_id, label, position),
                    ).lastrowid
                )
            return assignment_id, snapshot_ids

        def record_completions(snapshot_ids, day, completed_positions):
            for position, snapshot_id in enumerate(snapshot_ids):
                is_completed = position in completed_positions
                connection.execute(
                    """INSERT INTO daily_checklist_completions
                       (assignment_checklist_item_id, completion_date,
                        is_completed, completed_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        snapshot_id,
                        day.isoformat(),
                        int(is_completed),
                        f"{day.isoformat()}T18:00:00Z" if is_completed else None,
                    ),
                )

        kitchen_id, kitchen_items = create_chore(
            "Kitchen",
            "Wipe and sweep after dinner.",
            ("Wipe counters", "Sweep floor", "Take out trash"),
        )
        bathroom_id, bathroom_items = create_chore(
            "Bathroom",
            "Clean the bathroom.",
            ("Clean sink", "Scrub tub"),
        )
        yard_id, yard_items = create_chore(
            "Yard",
            "Maintain the yard.",
            ("Mow lawn", "Rake leaves"),
        )
        laundry_id, laundry_items = create_chore(
            "Laundry",
            "Wash and fold clothes.",
            ("Wash clothes", "Fold clothes"),
        )

        # Current week: Alex and Sam have active assignments; Riley does not.
        assign(
            "Alex",
            kitchen_id,
            kitchen_items,
            week_start,
            week_end,
            "Kitchen",
            "Wipe and sweep after dinner.",
        )
        assign(
            "Sam",
            bathroom_id,
            bathroom_items,
            week_start,
            week_end,
            "Bathroom",
            "Clean the bathroom.",
        )

        # Previous week provides complete, incomplete, and unrecorded days.
        _, yard_snapshots = assign(
            "Alex",
            yard_id,
            yard_items,
            prior_start,
            prior_end,
            "Yard",
            "Maintain the yard.",
        )
        record_completions(yard_snapshots, prior_start + timedelta(days=1), {0, 1})
        record_completions(yard_snapshots, prior_start + timedelta(days=2), {0})

        _, laundry_snapshots = assign(
            "Sam",
            laundry_id,
            laundry_items,
            prior_start,
            prior_end,
            "Laundry",
            "Wash and fold clothes.",
        )
        record_completions(laundry_snapshots, prior_start + timedelta(days=3), {0, 1})

        _, avery_snapshots = assign(
            "Avery",
            kitchen_id,
            kitchen_items,
            prior_start,
            prior_end,
            "Kitchen",
            "Wipe and sweep after dinner.",
        )
        for day_index in range(7):
            record_completions(
                avery_snapshots, prior_start + timedelta(days=day_index), {0, 1, 2}
            )

        _, jordan_snapshots = assign(
            "Jordan",
            bathroom_id,
            bathroom_items,
            prior_start,
            prior_end,
            "Bathroom",
            "Clean the bathroom.",
        )
        record_completions(jordan_snapshots, prior_start, {0, 1})
        record_completions(jordan_snapshots, prior_start + timedelta(days=1), {0, 1})

        assign(
            "Morgan",
            laundry_id,
            laundry_items,
            prior_start,
            prior_end,
            "Laundry",
            "Wash and fold clothes.",
        )

        _, taylor_snapshots = assign(
            "Taylor",
            yard_id,
            yard_items,
            prior_start,
            prior_end,
            "Yard",
            "Maintain the yard.",
        )
        for day_index in range(5):
            record_completions(
                taylor_snapshots, prior_start + timedelta(days=day_index), {0, 1}
            )

        # Two weeks prior supplies a second, fully complete report for history.
        _, older_alex_snapshots = assign(
            "Alex",
            bathroom_id,
            bathroom_items,
            older_start,
            older_end,
            "Bathroom",
            "Clean the bathroom.",
        )
        _, older_sam_snapshots = assign(
            "Sam",
            kitchen_id,
            kitchen_items,
            older_start,
            older_end,
            "Kitchen",
            "Wipe and sweep after dinner.",
        )
        _, older_avery_snapshots = assign(
            "Avery",
            laundry_id,
            laundry_items,
            older_start,
            older_end,
            "Laundry",
            "Wash and fold clothes.",
        )
        older_assignments = (
            (older_alex_snapshots, 2),
            (older_sam_snapshots, 3),
            (older_avery_snapshots, 2),
        )
        for snapshots, item_count in older_assignments:
            for day_index in range(7):
                record_completions(
                    snapshots,
                    older_start + timedelta(days=day_index),
                    set(range(item_count)),
                )

        connection.commit()
    finally:
        connection.close()

    from chore_tracker.adapters.sqlite.weekly_reports import (
        SQLiteWeeklyReportPersistence,
    )
    from chore_tracker.application.services.weekly_reports import (
        WeeklyReportService,
    )

    def report_generated_at(week_start):
        return datetime.combine(
            week_start + timedelta(days=7),
            time(3, 0),
            tzinfo=ZoneInfo(REPORT_TIMEZONE),
        ).astimezone(UTC)

    service = WeeklyReportService(
        SQLiteWeeklyReportPersistence(DATABASE_PATH), REPORT_TIMEZONE
    )
    service.generate(older_start, generated_at=report_generated_at(older_start))
    service.generate(prior_start, generated_at=report_generated_at(prior_start))


def set_test_today(value: date) -> None:
    """Move the child-facing date without changing the process clock."""
    global test_today
    test_today = value


def seed_lifecycle_catalog() -> dict[str, dict[str, int]]:
    """Seed a small catalog with enough active chores for real generation."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        members: dict[str, int] = {}
        for name in ("Alex", "Riley", "Sam"):
            member_id = connection.execute(
                "INSERT INTO family_members (display_name, is_active) VALUES (?, 1)",
                (name,),
            ).lastrowid
            if member_id is None:
                raise RuntimeError("The lifecycle member insert did not return an ID")
            members[name] = member_id

        chores: dict[str, int] = {}
        for name, description, labels in (
            ("Bathroom", "Clean the bathroom.", ("Clean sink",)),
            (
                "Kitchen",
                "Wipe and sweep after dinner.",
                ("Wipe counters", "Sweep floor"),
            ),
            ("Yard", "Maintain the yard.", ("Mow lawn", "Rake leaves")),
        ):
            chore_id = connection.execute(
                """INSERT INTO chores (name, description, is_active)
                   VALUES (?, ?, 1)""",
                (name, description),
            ).lastrowid
            if chore_id is None:
                raise RuntimeError("The lifecycle chore insert did not return an ID")
            for position, label in enumerate(labels):
                connection.execute(
                    """INSERT INTO chore_checklist_items
                       (chore_id, label, position, is_active)
                       VALUES (?, ?, ?, 1)""",
                    (chore_id, label, position),
                )
            chores[name] = chore_id

        connection.commit()
    finally:
        connection.close()
    return {"members": members, "chores": chores}


def assignment_service():
    from chore_tracker.adapters.sqlite.weekly_assignments import (
        SQLiteWeeklyAssignmentPersistence,
    )
    from chore_tracker.application.services.weekly_assignment_generation import (
        WeeklyAssignmentGenerationService,
    )

    return WeeklyAssignmentGenerationService(
        SQLiteWeeklyAssignmentPersistence(DATABASE_PATH), REPORT_TIMEZONE
    )


def report_service():
    from chore_tracker.adapters.sqlite.weekly_reports import (
        SQLiteWeeklyReportPersistence,
    )
    from chore_tracker.application.services.weekly_reports import WeeklyReportService

    return WeeklyReportService(
        SQLiteWeeklyReportPersistence(DATABASE_PATH), REPORT_TIMEZONE
    )


def rollover_service():
    from chore_tracker.adapters.sqlite.weekly_rollover import (
        SQLiteWeeklyRolloverPersistence,
    )
    from chore_tracker.application.services.weekly_rollover import (
        WeeklyRolloverService,
    )

    return WeeklyRolloverService(
        reports=report_service(),
        assignments=assignment_service(),
        persistence=SQLiteWeeklyRolloverPersistence(DATABASE_PATH),
        timezone_name=REPORT_TIMEZONE,
        delivery_time=time(3, 0),
    )


def reset_lifecycle_catalog() -> dict[str, dict[str, int]]:
    reset_database()
    catalog = seed_lifecycle_catalog()
    set_test_today(E2E_TODAY)
    return catalog


def reset_rollover_scenario() -> dict[str, dict[str, int]]:
    """Seed prior-week assignments and completions without generating its report."""
    reset_database()
    catalog = seed_lifecycle_catalog()
    prior_start = E2E_TODAY - timedelta(days=7)
    assignments = assignment_service().generate(prior_start, generated_on=prior_start)
    by_member = {assignment.family_member_id: assignment for assignment in assignments}

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        for member_name, completed_days in (("Alex", 7), ("Riley", 3)):
            assignment = by_member[catalog["members"][member_name]]
            for day_index in range(completed_days):
                day = prior_start + timedelta(days=day_index)
                for item in assignment.checklist_items:
                    connection.execute(
                        """INSERT INTO daily_checklist_completions (
                            assignment_checklist_item_id, completion_date,
                            is_completed, completed_at
                        ) VALUES (?, ?, 1, ?)""",
                        (
                            item.id,
                            day.isoformat(),
                            f"{day.isoformat()}T18:00:00Z",
                        ),
                    )
        connection.commit()
    finally:
        connection.close()

    set_test_today(E2E_TODAY)
    return catalog


def assignment_payload(assignments) -> list[dict[str, object]]:
    return [
        {
            "id": assignment.id,
            "family_member_id": assignment.family_member_id,
            "chore_id": assignment.chore_id,
            "week_start": assignment.week_start.isoformat(),
            "week_end": assignment.week_end.isoformat(),
            "chore_name": assignment.chore_name,
            "checklist_items": [
                {"id": item.id, "label": item.label, "position": item.position}
                for item in assignment.checklist_items
            ],
        }
        for assignment in assignments
    ]


def report_payload(report) -> dict[str, object]:
    return {
        "id": report.id,
        "week_start": report.week_start.isoformat(),
        "week_end": report.week_end.isoformat(),
        "generated_at": report.generated_at.isoformat(),
        "summary": {
            "family_member_count": report.summary.family_member_count,
            "total_days": report.summary.total_days,
            "completed_days": report.summary.completed_days,
            "incomplete_days": report.summary.incomplete_days,
        },
        "entries": [
            {
                "family_member_name": entry.family_member_name,
                "chore_name": entry.chore_name,
                "completed_days": entry.completed_days,
                "incomplete_days": entry.incomplete_days,
                "days": [
                    {
                        "date": day.report_date.isoformat(),
                        "status": day.status.value,
                    }
                    for day in entry.days
                ],
            }
            for entry in report.entries
        ],
    }


def install_test_hooks():
    """Attach isolated fixture controls to the real application for e2e tests."""
    from chore_tracker.main import app

    router = APIRouter(prefix="/__test__")

    @router.post("/reset", include_in_schema=False)
    def reset_fixture() -> dict[str, str]:
        reset_database()
        seed_database()
        set_test_today(E2E_TODAY)
        return {"status": "ok", "today": E2E_TODAY.isoformat()}

    @router.post("/scenario/rotation", include_in_schema=False)
    def reset_rotation_scenario() -> dict[str, dict[str, int]]:
        return reset_lifecycle_catalog()

    @router.post("/scenario/rollover", include_in_schema=False)
    def reset_rollover_fixture() -> dict[str, dict[str, int]]:
        return reset_rollover_scenario()

    @router.post("/today", include_in_schema=False)
    def set_fixture_today(body: TodayBody) -> dict[str, str]:
        set_test_today(body.date)
        return {"today": body.date.isoformat()}

    @router.post("/rotate", include_in_schema=False)
    def rotate_fixture(body: WeekBody) -> dict[str, object]:
        assignments = assignment_service().generate(
            body.week_start, generated_on=body.week_start
        )
        return {"assignments": assignment_payload(assignments)}

    @router.post("/rollover", include_in_schema=False)
    def rollover_fixture(body: RolloverBody) -> dict[str, object]:
        results = rollover_service().run_due(body.now)
        return {
            "results": [
                {
                    "assignment_week_start": result.assignment_week_start.isoformat(),
                    "report_week_start": result.report_week_start.isoformat(),
                    "report_id": result.report_id,
                    "assignment_count": result.assignment_count,
                }
                for result in results
            ]
        }

    @router.get("/counts", include_in_schema=False)
    def fixture_counts() -> dict[str, int]:
        tables = (
            "family_members",
            "chores",
            "weekly_assignments",
            "weekly_assignment_generations",
            "daily_checklist_completions",
            "weekly_reports",
            "weekly_report_entries",
            "weekly_report_days",
            "weekly_rollover_state",
        )
        connection = sqlite3.connect(DATABASE_PATH)
        try:
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            }
        finally:
            connection.close()

    @router.get("/report/{week_start}", include_in_schema=False)
    def fixture_report(week_start: date) -> dict[str, object]:
        report = report_service().get_report(week_start)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report_payload(report)

    app.include_router(router)
    app.state.child_views_today = lambda: test_today
    return app


def main() -> None:
    configure_environment()
    reset_database()
    seed_database()
    app = install_test_hooks()

    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=BACKEND_PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
