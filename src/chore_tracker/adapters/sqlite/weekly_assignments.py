"""SQLite persistence for weekly assignment generation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.application.services.weekly_assignment_generation import (
    AssignmentChecklistSnapshot,
    WeeklyAssignment,
    WeeklyAssignmentGenerationResult,
)
from chore_tracker.application.services.weekly_rotation import (
    RotationChore,
    RotationFamilyMember,
    first_assignment_week,
    plan_weekly_assignments,
)


class SQLiteWeeklyAssignmentPersistence:
    """Persist a complete weekly generation atomically in SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def rotation_anchor(self) -> date | None:
        """Return the immutable rotation anchor, if generation has started."""
        with transaction(self._database_path) as connection:
            row = connection.execute(
                "SELECT first_week_start FROM assignment_rotation_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return date.fromisoformat(row["first_week_start"])

    @staticmethod
    def _load_week_assignments(
        connection, week_start: date
    ) -> tuple[WeeklyAssignment, ...]:
        rows = connection.execute(
            """SELECT assignment.id, assignment.family_member_id,
                      member.display_name AS family_member_name,
                      assignment.chore_id, assignment.week_start,
                      assignment.week_end, assignment.chore_name_snapshot,
                      assignment.chore_description_snapshot
               FROM weekly_assignments AS assignment
               JOIN family_members AS member
                 ON member.id = assignment.family_member_id
               WHERE assignment.week_start = ? ORDER BY assignment.id""",
            (week_start.isoformat(),),
        ).fetchall()
        assignments = []
        for row in rows:
            checklist_rows = connection.execute(
                """SELECT id, source_checklist_item_id, label_snapshot, position,
                          is_required
                   FROM assignment_checklist_items
                   WHERE weekly_assignment_id = ? ORDER BY position, id""",
                (row["id"],),
            ).fetchall()
            assignments.append(
                WeeklyAssignment(
                    id=row["id"],
                    family_member_id=row["family_member_id"],
                    family_member_name=row["family_member_name"],
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
                            is_required=bool(item["is_required"]),
                        )
                        for item in checklist_rows
                    ),
                )
            )
        return tuple(assignments)

    def generate(
        self, week_start: date, week_end: date, generated_on: date
    ) -> WeeklyAssignmentGenerationResult:
        with transaction(self._database_path) as connection:
            # Serialize competing generators before checking the unique week record.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT week_start FROM weekly_assignment_generations
                   WHERE week_start = ?""",
                (week_start.isoformat(),),
            ).fetchone()
            if existing is not None:
                return WeeklyAssignmentGenerationResult(
                    week_start=week_start,
                    week_end=week_end,
                    created=False,
                    assignments=self._load_week_assignments(connection, week_start),
                )

            rotation_state = connection.execute(
                "SELECT first_week_start FROM assignment_rotation_state WHERE id = 1"
            ).fetchone()
            if rotation_state is None:
                rotation_anchor = first_assignment_week(generated_on)
                connection.execute(
                    """INSERT INTO assignment_rotation_state (id, first_week_start)
                       VALUES (1, ?)""",
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
                    """SELECT id, display_name, is_active FROM family_members
                       WHERE is_active = 1 ORDER BY display_name COLLATE NOCASE, id"""
                ).fetchall()
            ]
            chores = [
                RotationChore(
                    id=row["id"], name=row["name"], is_active=bool(row["is_active"])
                )
                for row in connection.execute(
                    """SELECT id, name, is_active FROM chores
                       WHERE is_active = 1 ORDER BY name COLLATE NOCASE, id"""
                ).fetchall()
            ]
            plan = plan_weekly_assignments(
                family_members, chores, week_start, rotation_anchor
            )

            connection.execute(
                """INSERT INTO weekly_assignment_generations
                   (week_start, week_end, rotation_anchor) VALUES (?, ?, ?)""",
                (
                    week_start.isoformat(),
                    week_end.isoformat(),
                    rotation_anchor.isoformat(),
                ),
            )
            for planned in plan:
                chore = connection.execute(
                    "SELECT name, description FROM chores WHERE id = ?",
                    (planned.chore_id,),
                ).fetchone()
                assignment_id = connection.execute(
                    """INSERT INTO weekly_assignments
                       (family_member_id, chore_id, week_start, week_end,
                        chore_name_snapshot, chore_description_snapshot)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        planned.family_member_id,
                        planned.chore_id,
                        week_start.isoformat(),
                        week_end.isoformat(),
                        chore["name"],
                        chore["description"],
                    ),
                ).lastrowid
                items = connection.execute(
                    """SELECT id, label, position, is_required
                       FROM chore_checklist_items
                       WHERE chore_id = ? AND is_active = 1 ORDER BY position, id""",
                    (planned.chore_id,),
                ).fetchall()
                for item in items:
                    connection.execute(
                        """INSERT INTO assignment_checklist_items
                           (weekly_assignment_id, source_checklist_item_id,
                            label_snapshot, position, is_required)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            assignment_id,
                            item["id"],
                            item["label"],
                            item["position"],
                            int(item["is_required"]),
                        ),
                    )
            return WeeklyAssignmentGenerationResult(
                week_start=week_start,
                week_end=week_end,
                created=True,
                assignments=self._load_week_assignments(connection, week_start),
            )
