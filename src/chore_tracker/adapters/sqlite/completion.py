"""SQLite persistence for daily completion and completion history."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from chore_tracker.adapters.sqlite import transaction


class SQLiteCompletionPersistence:
    """Own SQLite queries and transactions for completion use cases."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def _assignment(self, connection, family_member_id: int, assignment_id: int, completion_date: date) -> None:
        member = connection.execute("SELECT is_active FROM family_members WHERE id = ?", (family_member_id,)).fetchone()
        if member is None:
            raise _PersistenceError(404, "Family member was not found")
        if not member["is_active"]:
            raise _PersistenceError(409, "Family member is inactive")
        assignment = connection.execute(
            "SELECT id, week_start, week_end FROM weekly_assignments WHERE id = ? AND family_member_id = ?",
            (assignment_id, family_member_id),
        ).fetchone()
        if assignment is None:
            raise _PersistenceError(404, "Weekly assignment was not found")
        value = completion_date.isoformat()
        if not assignment["week_start"] <= value <= assignment["week_end"]:
            raise _PersistenceError(422, "Completion date must be within the weekly assignment")

    def _daily(self, connection, assignment_id: int, completion_date: date) -> dict[str, Any]:
        rows = connection.execute(
            """SELECT snapshot.id, snapshot.label_snapshot, snapshot.position,
                      COALESCE(completion.is_completed, 0) AS is_completed
               FROM assignment_checklist_items AS snapshot
               LEFT JOIN daily_checklist_completions AS completion
                 ON completion.assignment_checklist_item_id = snapshot.id
                AND completion.completion_date = ?
               WHERE snapshot.weekly_assignment_id = ?
               ORDER BY snapshot.position, snapshot.id""",
            (completion_date.isoformat(), assignment_id),
        ).fetchall()
        items = [{"id": row["id"], "label": row["label_snapshot"], "position": row["position"], "is_completed": bool(row["is_completed"])} for row in rows]
        return {"assignment_id": assignment_id, "completion_date": completion_date, "checklist_items": items, "is_complete": bool(items) and all(item["is_completed"] for item in items)}

    def get_daily_completion(self, family_member_id: int, assignment_id: int, completion_date: date) -> dict[str, Any]:
        with transaction(self._database_path) as connection:
            self._assignment(connection, family_member_id, assignment_id, completion_date)
            return self._daily(connection, assignment_id, completion_date)

    def set_checklist_item_completion(self, family_member_id: int, assignment_id: int, checklist_item_id: int, completion_date: date, is_completed: bool) -> dict[str, Any]:
        with transaction(self._database_path) as connection:
            self._assignment(connection, family_member_id, assignment_id, completion_date)
            item = connection.execute(
                "SELECT id FROM assignment_checklist_items WHERE id = ? AND weekly_assignment_id = ?",
                (checklist_item_id, assignment_id),
            ).fetchone()
            if item is None:
                raise _PersistenceError(404, "Checklist item was not found in the weekly assignment")
            completed_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z") if is_completed else None
            connection.execute(
                """INSERT INTO daily_checklist_completions
                   (assignment_checklist_item_id, completion_date, is_completed, completed_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (assignment_checklist_item_id, completion_date)
                   DO UPDATE SET is_completed = excluded.is_completed,
                     completed_at = CASE
                       WHEN daily_checklist_completions.is_completed = excluded.is_completed
                       THEN daily_checklist_completions.completed_at
                       ELSE excluded.completed_at END""",
                (checklist_item_id, completion_date.isoformat(), int(is_completed), completed_at),
            )
            state = self._daily(connection, assignment_id, completion_date)
            updated = next(value for value in state["checklist_items"] if value["id"] == checklist_item_id)
            return {"assignment_id": assignment_id, "completion_date": completion_date, "checklist_item": updated, "is_complete": state["is_complete"]}

    def get_completion_history(self, family_member_id: int, limit: int, offset: int) -> dict[str, Any] | None:
        with transaction(self._database_path) as connection:
            if connection.execute("SELECT id FROM family_members WHERE id = ?", (family_member_id,)).fetchone() is None:
                return None
            total = connection.execute("SELECT COUNT(*) * 7 FROM weekly_assignments WHERE family_member_id = ?", (family_member_id,)).fetchone()[0]
            rows = connection.execute(
                """WITH RECURSIVE assignment_days AS (
                     SELECT id AS assignment_id, week_start, week_end, chore_name_snapshot,
                            chore_description_snapshot, week_start AS completion_date
                     FROM weekly_assignments WHERE family_member_id = ?
                     UNION ALL
                     SELECT assignment_id, week_start, week_end, chore_name_snapshot,
                            chore_description_snapshot, date(completion_date, '+1 day')
                     FROM assignment_days WHERE completion_date < week_end
                   ), checklist_counts AS (
                     SELECT weekly_assignment_id, COUNT(*) AS item_count
                     FROM assignment_checklist_items GROUP BY weekly_assignment_id
                   ), daily_completion_counts AS (
                     SELECT item.weekly_assignment_id, completion.completion_date,
                            COUNT(*) AS recorded_count, SUM(completion.is_completed) AS completed_count
                     FROM assignment_checklist_items AS item
                     JOIN daily_checklist_completions AS completion
                       ON completion.assignment_checklist_item_id = item.id
                     GROUP BY item.weekly_assignment_id, completion.completion_date
                   )
                   SELECT day.assignment_id, day.week_start, day.week_end,
                          day.chore_name_snapshot, day.chore_description_snapshot,
                          day.completion_date,
                          CASE WHEN COALESCE(checklist.item_count, 0) = 0
                                    OR COALESCE(daily.recorded_count, 0) = 0
                               THEN 'not_yet_recorded'
                               WHEN daily.completed_count = checklist.item_count THEN 'complete'
                               ELSE 'incomplete' END AS completion_status
                   FROM assignment_days AS day
                   LEFT JOIN checklist_counts AS checklist ON checklist.weekly_assignment_id = day.assignment_id
                   LEFT JOIN daily_completion_counts AS daily
                     ON daily.weekly_assignment_id = day.assignment_id
                    AND daily.completion_date = day.completion_date
                   ORDER BY day.completion_date DESC, day.assignment_id DESC
                   LIMIT ? OFFSET ?""",
                (family_member_id, limit, offset),
            ).fetchall()
            return {"items": [{"assignment_id": row["assignment_id"], "week_start": row["week_start"], "week_end": row["week_end"], "chore_name": row["chore_name_snapshot"], "chore_description": row["chore_description_snapshot"], "completion_date": row["completion_date"], "completion_status": row["completion_status"]} for row in rows], "total": total, "limit": limit, "offset": offset}


class _PersistenceError(Exception):
    """Storage result carrying an application-facing status/detail contract."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
