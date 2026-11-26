#!/usr/bin/env bash
# Verify the documented SQLite backup and restore procedure against a sample
# database that contains assignments, completions, and a finalized report.
#
# This script uses only the application's migrations and services. It is safe
# to run locally or in CI; all files live in a temporary directory.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON="${PYTHON:-python}"
workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

database="${workdir}/chore-tracker.db"
failed_database="${workdir}/chore-tracker.failed.db"
backup="${workdir}/chore-tracker-backup.db"

export CHORE_TRACKER_DATABASE_PATH="${database}"

echo "Applying migrations to a fresh sample database"
"${PYTHON}" -m alembic upgrade head >/dev/null

echo "Seeding a week of history, a finalized report, and rollover state"
"${PYTHON}" - "${database}" <<'PY'
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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
from chore_tracker.application.services.weekly_reports import WeeklyReportService
from chore_tracker.application.services.weekly_rollover import WeeklyRolloverService

database_path = Path(sys.argv[1])
timezone = "America/Denver"
report_week = date(2026, 11, 16)
current_week = date(2026, 11, 23)
run_at = datetime(2026, 11, 23, 3, 0, tzinfo=ZoneInfo(timezone))

members = ("Alex", "Sam")
chores = (
    ("Kitchen", "Reset the kitchen", ("Sweep floor", "Wipe counters")),
    ("Bathroom", "Clean the bathroom", ("Clean sink",)),
    ("Laundry", "Wash the clothes", ("Sort laundry",)),
)

member_ids: dict[str, int] = {}
with connect(database_path) as connection:
    for member in members:
        member_ids[member] = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES (?, 1)",
            (member,),
        ).lastrowid
    for name, description, checklist in chores:
        chore_id = connection.execute(
            "INSERT INTO chores (name, description, is_active) VALUES (?, ?, 1)",
            (name, description),
        ).lastrowid
        for position, label in enumerate(checklist):
            connection.execute(
                """
                INSERT INTO chore_checklist_items
                    (chore_id, label, position, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (chore_id, label, position),
            )
    administrator_id = connection.execute(
        "INSERT INTO administrators (email) VALUES ('admin@example.test')"
    ).lastrowid

assignments = WeeklyAssignmentGenerationService(
    SQLiteWeeklyAssignmentPersistence(database_path), timezone
).generate(report_week, generated_on=report_week).assignments
by_member = {assignment.family_member_id: assignment for assignment in assignments}

with connect(database_path) as connection:
    for day_offset in range(7):
        day = report_week + timedelta(days=day_offset)
        for item in by_member[member_ids["Alex"]].checklist_items:
            connection.execute(
                """
                INSERT INTO daily_checklist_completions
                    (assignment_checklist_item_id, completion_date,
                     is_completed, completed_at)
                VALUES (?, ?, 1, ?)
                """,
                (item.id, day.isoformat(), f"{day.isoformat()}T18:00:00Z"),
            )
    for day_offset in range(3):
        day = report_week + timedelta(days=day_offset)
        for item in by_member[member_ids["Sam"]].checklist_items:
            connection.execute(
                """
                INSERT INTO daily_checklist_completions
                    (assignment_checklist_item_id, completion_date,
                     is_completed, completed_at)
                VALUES (?, ?, 1, ?)
                """,
                (item.id, day.isoformat(), f"{day.isoformat()}T18:00:00Z"),
            )

results = WeeklyRolloverService(
    reports=WeeklyReportService(
        SQLiteWeeklyReportPersistence(database_path), timezone
    ),
    assignments=WeeklyAssignmentGenerationService(
        SQLiteWeeklyAssignmentPersistence(database_path), timezone
    ),
    persistence=SQLiteWeeklyRolloverPersistence(database_path),
    timezone_name=timezone,
    delivery_time=time(3, 0),
).run_due(run_at)

assert len(results) == 1, results
assert results[0].report_week_start == report_week
assert results[0].assignment_week_start == current_week

with connect(database_path) as connection:
    rewarded_entry_id = connection.execute(
        "SELECT id FROM weekly_report_entries ORDER BY position LIMIT 1"
    ).fetchone()["id"]
    connection.execute(
        """
        INSERT INTO weekly_report_rewards (
            weekly_report_entry_id, rewarded_at, rewarded_by_administrator_id
        )
        VALUES (?, '2026-11-23T11:00:00Z', ?)
        """,
        (rewarded_entry_id, administrator_id),
    )
PY

echo "Backing up the database with SQLite's online backup API"
"${PYTHON}" - "${database}" "${backup}" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
finally:
    target.close()
    source.close()

with sqlite3.connect(sys.argv[2]) as backup_check:
    assert backup_check.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert backup_check.execute("PRAGMA foreign_key_check").fetchall() == []
PY

echo "Simulating loss of the source database and restoring the backup"
mv "${database}" "${failed_database}"
cp "${backup}" "${database}"

echo "Verifying the restored database"
"${PYTHON}" - "${backup}" "${database}" <<'PY'
import hashlib
import sqlite3
import sys
from datetime import date

from chore_tracker.adapters.sqlite.weekly_reports import SQLiteWeeklyReportPersistence
from chore_tracker.adapters.sqlite.weekly_rollover import (
    SQLiteWeeklyRolloverPersistence,
)
from chore_tracker.application.services.weekly_reports import WeeklyReportService

backup_path, restored_path = sys.argv[1], sys.argv[2]
report_week = date(2026, 11, 16)
expected_checkpoint = date(2026, 11, 23)

tables = (
    "administrators",
    "family_members",
    "chores",
    "chore_checklist_items",
    "weekly_assignments",
    "assignment_checklist_items",
    "daily_checklist_completions",
    "weekly_reports",
    "weekly_report_entries",
    "weekly_report_days",
    "weekly_report_rewards",
    "assignment_rotation_state",
    "weekly_assignment_generations",
    "weekly_rollover_state",
)


def fingerprint(path: str) -> str:
    digest = hashlib.sha256()
    with sqlite3.connect(path) as connection:
        for table in tables:
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            digest.update(f"{table}:{len(rows)}\n".encode())
            for row in rows:
                digest.update(repr(row).encode())
                digest.update(b"\n")
    return digest.hexdigest()


backup_digest = fingerprint(backup_path)
restored_digest = fingerprint(restored_path)
assert backup_digest == restored_digest, "restored data does not match the backup"

with sqlite3.connect(restored_path) as connection:
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    def count(table: str) -> int:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    assignments = count("weekly_assignments")
    completions = count("daily_checklist_completions")
    reports = count("weekly_reports")
    report_entries = count("weekly_report_entries")
    report_days = count("weekly_report_days")
    report_rewards = count("weekly_report_rewards")

report = WeeklyReportService(
    SQLiteWeeklyReportPersistence(restored_path), "America/Denver"
).get_report(report_week)
assert report is not None, "restored weekly report is missing"
assert report.summary.family_member_count == 2
assert report.summary.completed_days == 10
assert report.summary.total_days == 14
assert report.entries[0].completed_days == 7
rewarded_entry = next(
    entry for entry in report.entries if entry.family_member_name == "Alex"
)
assert rewarded_entry.reward is not None, "restored report reward is missing"
assert rewarded_entry.reward.administrator_email == "admin@example.test"

checkpoint = SQLiteWeeklyRolloverPersistence(restored_path).last_completed_week_start()
assert checkpoint == expected_checkpoint, checkpoint

assert assignments == 4, assignments
assert completions == 13, completions
assert reports == 1, reports
assert report_entries == 2, report_entries
assert report_days == 14, report_days
assert report_rewards == 1, report_rewards

print("Backup and restore verification passed")
print(f"  assignment rows: {assignments} (two weeks x two children)")
print(f"  completion rows: {completions}")
print(f"  weekly reports: {reports} ({report_entries} entries, {report_days} day snapshots)")
print(f"  report reward rows: {report_rewards}")
print(f"  report totals: {report.summary.completed_days}/{report.summary.total_days} completed days")
print(f"  rollover checkpoint: {checkpoint}")
print(f"  data fingerprint: {restored_digest[:16]}...")
PY
