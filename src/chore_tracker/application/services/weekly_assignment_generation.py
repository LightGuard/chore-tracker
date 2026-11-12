"""Generate and persist immutable Monday–Sunday weekly assignments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.application.services.weekly_rotation import (
    RotationChore,
    RotationFamilyMember,
    WeeklyAssignmentPlan,
    first_assignment_week,
    plan_weekly_assignments,
)
from chore_tracker.config import get_settings


@dataclass(frozen=True, slots=True)
class AssignmentChecklistSnapshot:
    """An ordered checklist item captured when a weekly assignment is created."""

    id: int
    source_checklist_item_id: int | None
    label: str
    position: int


@dataclass(frozen=True, slots=True)
class WeeklyAssignment:
    """Persisted weekly assignment and its immutable chore/checklist snapshots."""

    id: int
    family_member_id: int
    chore_id: int
    week_start: date
    week_end: date
    chore_name: str
    chore_description: str
    checklist_items: tuple[AssignmentChecklistSnapshot, ...]


def _week_start(value: date | datetime, timezone: ZoneInfo) -> date:
    """Normalize a date or aware datetime to the Monday of its local calendar week."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("week must be a date or timezone-aware datetime")
        local_date = value.astimezone(timezone).date()
    elif isinstance(value, date):
        local_date = value
    else:
        raise TypeError("week must be a date or timezone-aware datetime")
    return local_date - timedelta(days=local_date.weekday())


def _load_week_assignments(
    connection, week_start: date
) -> tuple[WeeklyAssignment, ...]:
    rows = connection.execute(
        """
        SELECT id, family_member_id, chore_id, week_start, week_end,
               chore_name_snapshot, chore_description_snapshot
        FROM weekly_assignments
        WHERE week_start = ?
        ORDER BY id
        """,
        (week_start.isoformat(),),
    ).fetchall()

    assignments = []
    for row in rows:
        checklist_rows = connection.execute(
            """
            SELECT id, source_checklist_item_id, label_snapshot, position
            FROM assignment_checklist_items
            WHERE weekly_assignment_id = ?
            ORDER BY position, id
            """,
            (row["id"],),
        ).fetchall()
        assignments.append(
            WeeklyAssignment(
                id=row["id"],
                family_member_id=row["family_member_id"],
                chore_id=row["chore_id"],
                week_start=date.fromisoformat(row["week_start"]),
                week_end=date.fromisoformat(row["week_end"]),
                chore_name=row["chore_name_snapshot"],
                chore_description=row["chore_description_snapshot"],
                checklist_items=tuple(
                    AssignmentChecklistSnapshot(
                        id=item["id"],
                        source_checklist_item_id=item["source_checklist_item_id"],
                        label=item["label_snapshot"],
                        position=item["position"],
                    )
                    for item in checklist_rows
                ),
            )
        )
    return tuple(assignments)


def generate_weekly_assignments(
    week: date | datetime,
    *,
    database_path: str | Path | None = None,
    timezone_name: str | None = None,
    generated_on: date | None = None,
) -> tuple[WeeklyAssignment, ...]:
    """Generate one week's assignments, or return the existing immutable result.

    The week is interpreted in the configured calendar timezone and normalized
    to its Monday. generated_on is an injectable local date for deterministic
    tests; normal application calls use the current date in that timezone.
    """
    settings = get_settings()
    timezone = ZoneInfo(timezone_name or settings.report_timezone)
    normalized_week_start = _week_start(week, timezone)
    week_end = normalized_week_start + timedelta(days=6)
    path = database_path if database_path is not None else settings.database_path

    if generated_on is not None and isinstance(generated_on, datetime):
        raise TypeError("generated_on must be a date, not a datetime")
    local_generation_date = generated_on or datetime.now(timezone).date()

    with transaction(path) as connection:
        # Serialize competing generators before checking the unique week record.
        connection.execute("BEGIN IMMEDIATE")

        existing_generation = connection.execute(
            """
            SELECT week_start
            FROM weekly_assignment_generations
            WHERE week_start = ?
            """,
            (normalized_week_start.isoformat(),),
        ).fetchone()
        if existing_generation is not None:
            return _load_week_assignments(connection, normalized_week_start)

        rotation_state = connection.execute(
            """
            SELECT first_week_start
            FROM assignment_rotation_state
            WHERE id = 1
            """
        ).fetchone()
        if rotation_state is None:
            rotation_anchor = first_assignment_week(local_generation_date)
            connection.execute(
                """
                INSERT INTO assignment_rotation_state (id, first_week_start)
                VALUES (1, ?)
                """,
                (rotation_anchor.isoformat(),),
            )
        else:
            rotation_anchor = date.fromisoformat(rotation_state["first_week_start"])

        family_members = [
            RotationFamilyMember(
                id=row["id"],
                display_name=row["display_name"],
                is_active=bool(row["is_active"]),
            )
            for row in connection.execute(
                """
                SELECT id, display_name, is_active
                FROM family_members
                WHERE is_active = 1
                ORDER BY display_name COLLATE NOCASE, id
                """
            ).fetchall()
        ]
        chores = [
            RotationChore(
                id=row["id"],
                name=row["name"],
                is_active=bool(row["is_active"]),
            )
            for row in connection.execute(
                """
                SELECT id, name, is_active
                FROM chores
                WHERE is_active = 1
                ORDER BY name COLLATE NOCASE, id
                """
            ).fetchall()
        ]
        plan: tuple[WeeklyAssignmentPlan, ...] = plan_weekly_assignments(
            family_members,
            chores,
            normalized_week_start,
            rotation_anchor,
        )

        connection.execute(
            """
            INSERT INTO weekly_assignment_generations (
                week_start, week_end, rotation_anchor
            )
            VALUES (?, ?, ?)
            """,
            (
                normalized_week_start.isoformat(),
                week_end.isoformat(),
                rotation_anchor.isoformat(),
            ),
        )

        for planned_assignment in plan:
            chore = connection.execute(
                """
                SELECT name, description
                FROM chores
                WHERE id = ?
                """,
                (planned_assignment.chore_id,),
            ).fetchone()
            assignment_id = connection.execute(
                """
                INSERT INTO weekly_assignments (
                    family_member_id, chore_id, week_start, week_end,
                    chore_name_snapshot, chore_description_snapshot
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    planned_assignment.family_member_id,
                    planned_assignment.chore_id,
                    normalized_week_start.isoformat(),
                    week_end.isoformat(),
                    chore["name"],
                    chore["description"],
                ),
            ).lastrowid

            checklist_items = connection.execute(
                """
                SELECT id, label, position
                FROM chore_checklist_items
                WHERE chore_id = ? AND is_active = 1
                ORDER BY position, id
                """,
                (planned_assignment.chore_id,),
            ).fetchall()
            for item in checklist_items:
                connection.execute(
                    """
                    INSERT INTO assignment_checklist_items (
                        weekly_assignment_id, source_checklist_item_id,
                        label_snapshot, position
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        assignment_id,
                        item["id"],
                        item["label"],
                        item["position"],
                    ),
                )

        return _load_week_assignments(connection, normalized_week_start)
