"""Start a disposable, seeded backend for Playwright browser tests."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = ROOT / "frontend" / ".playwright-data"
DATABASE_PATH = DATA_DIRECTORY / "chore-tracker-e2e.db"
BACKEND_PORT = 8001
FRONTEND_ORIGIN = "http://localhost:5174"
REPORT_TIMEZONE = "America/Denver"


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
            # The browser fixture seeds reports and current assignments directly.
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
    today = datetime.now(ZoneInfo(REPORT_TIMEZONE)).date()
    week_start = today - timedelta(days=today.weekday())
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


def main() -> None:
    configure_environment()
    reset_database()
    seed_database()

    import uvicorn

    uvicorn.run(
        "chore_tracker.main:app",
        host="127.0.0.1",
        port=BACKEND_PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
