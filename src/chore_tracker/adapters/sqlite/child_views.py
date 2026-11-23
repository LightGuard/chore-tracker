"""SQLite persistence for child-facing views and completion operations."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from chore_tracker.adapters.sqlite import transaction


class SQLiteChildViewsPersistence:
    """Own SQL, row mapping, and transaction boundaries for child views."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def list_active_family_members(self) -> list[dict[str, Any]]:
        with transaction(self._database_path) as connection:
            rows = connection.execute(
                """SELECT id, display_name, theme_id FROM family_members
                   WHERE is_active = 1
                   ORDER BY display_name COLLATE NOCASE, id"""
            ).fetchall()
            return [dict(row) for row in rows]

    def get_current_assignment(
        self, family_member_id: int, today: date
    ) -> dict[str, Any] | None:
        week_start = today - timedelta(days=today.weekday())
        with transaction(self._database_path) as connection:
            member = connection.execute(
                "SELECT is_active FROM family_members WHERE id = ?",
                (family_member_id,),
            ).fetchone()
            if member is None:
                return None
            if not member["is_active"]:
                return {"inactive": True}
            assignment = connection.execute(
                """SELECT id, family_member_id, week_start, week_end,
                          chore_name_snapshot, chore_description_snapshot
                   FROM weekly_assignments
                   WHERE family_member_id = ? AND week_start = ?""",
                (family_member_id, week_start.isoformat()),
            ).fetchone()
            if assignment is None:
                return {"assignment_missing": True}
            rows = connection.execute(
                """SELECT snapshot.id, snapshot.label_snapshot, snapshot.position,
                          COALESCE(completion.is_completed, 0) AS is_completed
                   FROM assignment_checklist_items AS snapshot
                   LEFT JOIN daily_checklist_completions AS completion
                     ON completion.assignment_checklist_item_id = snapshot.id
                    AND completion.completion_date = ?
                   WHERE snapshot.weekly_assignment_id = ?
                   ORDER BY snapshot.position, snapshot.id""",
                (today.isoformat(), assignment["id"]),
            ).fetchall()
            items = [
                {
                    "id": row["id"],
                    "label": row["label_snapshot"],
                    "position": row["position"],
                    "is_completed": bool(row["is_completed"]),
                }
                for row in rows
            ]
            return {
                "id": assignment["id"],
                "family_member_id": assignment["family_member_id"],
                "week_start": assignment["week_start"],
                "week_end": assignment["week_end"],
                "chore_name": assignment["chore_name_snapshot"],
                "chore_description": assignment["chore_description_snapshot"],
                "today": today,
                "checklist_items": items,
                "is_complete": bool(items)
                and all(item["is_completed"] for item in items),
            }

    def _assignment_for_date(self, connection, family_member_id, assignment_id, day):
        member = connection.execute(
            "SELECT is_active FROM family_members WHERE id = ?", (family_member_id,)
        ).fetchone()
        if member is None:
            return None, "member_missing"
        if not member["is_active"]:
            return None, "inactive"
        assignment = connection.execute(
            """SELECT id, week_start, week_end FROM weekly_assignments
               WHERE id = ? AND family_member_id = ?""",
            (assignment_id, family_member_id),
        ).fetchone()
        if assignment is None:
            return None, "assignment_missing"
        value = day.isoformat()
        if not assignment["week_start"] <= value <= assignment["week_end"]:
            return None, "date_outside_assignment"
        return assignment, None

    def _daily_completion(self, connection, assignment_id: int, day: date):
        rows = connection.execute(
            """SELECT snapshot.id, snapshot.label_snapshot, snapshot.position,
                      COALESCE(completion.is_completed, 0) AS is_completed
               FROM assignment_checklist_items AS snapshot
               LEFT JOIN daily_checklist_completions AS completion
                 ON completion.assignment_checklist_item_id = snapshot.id
                AND completion.completion_date = ?
               WHERE snapshot.weekly_assignment_id = ?
               ORDER BY snapshot.position, snapshot.id""",
            (day.isoformat(), assignment_id),
        ).fetchall()
        items = [
            {
                "id": row["id"],
                "label": row["label_snapshot"],
                "position": row["position"],
                "is_completed": bool(row["is_completed"]),
            }
            for row in rows
        ]
        return {
            "assignment_id": assignment_id,
            "completion_date": day,
            "checklist_items": items,
            "is_complete": bool(items) and all(item["is_completed"] for item in items),
        }

    @staticmethod
    def _error_result(error):
        return None if error == "member_missing" else {error: True}

    def get_assignment_completion(self, family_member_id, assignment_id, day):
        with transaction(self._database_path) as connection:
            assignment, error = self._assignment_for_date(
                connection, family_member_id, assignment_id, day
            )
            if error:
                return self._error_result(error)
            return {
                "completion": self._daily_completion(connection, assignment["id"], day)
            }

    def update_assignment_checklist_completion(
        self, family_member_id, assignment_id, checklist_item_id, day, is_completed
    ):
        with transaction(self._database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            assignment, error = self._assignment_for_date(
                connection, family_member_id, assignment_id, day
            )
            if error:
                return self._error_result(error)
            item = connection.execute(
                """SELECT id FROM assignment_checklist_items
                   WHERE id = ? AND weekly_assignment_id = ?""",
                (checklist_item_id, assignment_id),
            ).fetchone()
            if item is None:
                return {"item_missing": True}
            completed_at = (
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                if is_completed
                else None
            )
            connection.execute(
                """INSERT INTO daily_checklist_completions
                   (assignment_checklist_item_id, completion_date,
                    is_completed, completed_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (assignment_checklist_item_id, completion_date)
                   DO UPDATE SET is_completed = excluded.is_completed,
                     completed_at = CASE
                       WHEN daily_checklist_completions.is_completed
                            = excluded.is_completed
                       THEN daily_checklist_completions.completed_at
                       ELSE excluded.completed_at END""",
                (checklist_item_id, day.isoformat(), int(is_completed), completed_at),
            )
            daily = self._daily_completion(connection, assignment_id, day)
            updated = next(
                i for i in daily["checklist_items"] if i["id"] == checklist_item_id
            )
            return {
                "completion": {
                    "assignment_id": assignment_id,
                    "completion_date": day,
                    "checklist_item": updated,
                    "is_complete": daily["is_complete"],
                }
            }

    def get_derived_stats(self, family_member_id, today, week_start, week_end):
        """Read generic lifetime, current-week, and household completion facts."""
        with transaction(self._database_path) as connection:
            member_rows = connection.execute(
                """
                WITH RECURSIVE member_scope AS (
                  SELECT id, display_name, is_active, 1 AS is_selected
                  FROM family_members
                  WHERE id = :family_member_id
                  UNION ALL
                  SELECT id, display_name, is_active, 0
                  FROM family_members
                  WHERE is_active = 1 AND id != :family_member_id
                ),
                assignment_days AS (
                  SELECT assignment.id AS assignment_id,
                         assignment.family_member_id,
                         date(assignment.week_start) AS day,
                         assignment.week_end
                  FROM weekly_assignments AS assignment
                  WHERE assignment.family_member_id IN (
                    SELECT id FROM member_scope
                  )
                  UNION ALL
                  SELECT assignment_days.assignment_id,
                         assignment_days.family_member_id,
                         date(assignment_days.day, '+1 day'),
                         assignment_days.week_end
                  FROM assignment_days
                  WHERE assignment_days.day < assignment_days.week_end
                ),
                item_counts AS (
                  SELECT item.weekly_assignment_id, COUNT(*) AS total_items
                  FROM assignment_checklist_items AS item
                  WHERE item.weekly_assignment_id IN (
                    SELECT assignment_id FROM assignment_days
                  )
                  GROUP BY item.weekly_assignment_id
                ),
                completion_counts AS (
                  SELECT item.weekly_assignment_id,
                         completion.completion_date,
                         SUM(completion.is_completed) AS completed_items,
                         COUNT(*) AS recorded_items
                  FROM assignment_checklist_items AS item
                  JOIN daily_checklist_completions AS completion
                    ON completion.assignment_checklist_item_id = item.id
                  WHERE item.weekly_assignment_id IN (
                    SELECT assignment_id FROM assignment_days
                  )
                  GROUP BY item.weekly_assignment_id,
                           completion.completion_date
                ),
                day_facts AS (
                  SELECT assignment_days.family_member_id,
                         assignment_days.day,
                         COALESCE(items.total_items, 0) AS total_items,
                         COALESCE(completion.completed_items, 0)
                           AS completed_items,
                         CASE
                           WHEN COALESCE(items.total_items, 0) > 0
                            AND COALESCE(completion.completed_items, 0)
                                = items.total_items
                           THEN 1
                           ELSE 0
                         END AS is_complete
                  FROM assignment_days
                  LEFT JOIN item_counts AS items
                    ON items.weekly_assignment_id
                       = assignment_days.assignment_id
                  LEFT JOIN completion_counts AS completion
                    ON completion.weekly_assignment_id
                       = assignment_days.assignment_id
                   AND completion.completion_date = assignment_days.day
                ),
                streak_anchors AS (
                  SELECT scope.id AS family_member_id,
                         CASE
                           WHEN EXISTS (
                             SELECT 1
                             FROM day_facts AS fact
                             WHERE fact.family_member_id = scope.id
                               AND fact.day = :today
                               AND fact.is_complete = 1
                           ) THEN :today
                           WHEN EXISTS (
                             SELECT 1
                             FROM day_facts AS fact
                             WHERE fact.family_member_id = scope.id
                               AND fact.day = date(:today, '-1 day')
                               AND fact.is_complete = 1
                           ) THEN date(:today, '-1 day')
                           ELSE NULL
                         END AS anchor_day
                  FROM member_scope AS scope
                ),
                streak_days AS (
                  SELECT family_member_id, anchor_day AS day
                  FROM streak_anchors
                  WHERE anchor_day IS NOT NULL
                  UNION ALL
                  SELECT streak_days.family_member_id,
                         date(streak_days.day, '-1 day')
                  FROM streak_days
                  JOIN day_facts AS fact
                    ON fact.family_member_id = streak_days.family_member_id
                   AND fact.day = date(streak_days.day, '-1 day')
                   AND fact.is_complete = 1
                ),
                streak_counts AS (
                  SELECT family_member_id, COUNT(*) AS current_streak
                  FROM streak_days
                  GROUP BY family_member_id
                )
                SELECT scope.id AS family_member_id,
                       scope.display_name,
                       scope.is_active,
                       scope.is_selected,
                       COALESCE(SUM(
                         CASE
                           WHEN fact.day BETWEEN :week_start AND :week_end
                           THEN fact.completed_items
                           ELSE 0
                         END
                       ), 0) AS current_week_completed_items,
                       COALESCE(SUM(
                         CASE
                           WHEN fact.day BETWEEN :week_start AND :week_end
                            AND fact.is_complete = 1
                           THEN 1
                           ELSE 0
                         END
                       ), 0) AS current_week_complete_days,
                       COALESCE(SUM(fact.completed_items), 0)
                         AS lifetime_completed_items,
                       COALESCE(SUM(fact.is_complete), 0)
                         AS lifetime_complete_days,
                       COALESCE(streak.current_streak, 0)
                         AS current_streak
                FROM member_scope AS scope
                LEFT JOIN day_facts AS fact
                  ON fact.family_member_id = scope.id
                LEFT JOIN streak_counts AS streak
                  ON streak.family_member_id = scope.id
                GROUP BY scope.id, scope.display_name, scope.is_active,
                         scope.is_selected, streak.current_streak
                ORDER BY scope.is_selected DESC,
                         scope.display_name COLLATE NOCASE,
                         scope.id
                """,
                {
                    "family_member_id": family_member_id,
                    "today": today.isoformat(),
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                },
            ).fetchall()
            selected_row = next(
                (row for row in member_rows if row["is_selected"]), None
            )
            if selected_row is None:
                return None
            week_rows = connection.execute(
                """
                WITH RECURSIVE week_days(day) AS (
                  SELECT date(:week_start)
                  UNION ALL
                  SELECT date(day, '+1 day')
                  FROM week_days
                  WHERE day < date(:week_end)
                ),
                current_assignment AS (
                  SELECT id
                  FROM weekly_assignments
                  WHERE family_member_id = :family_member_id
                    AND week_start = :week_start
                ),
                item_counts AS (
                  SELECT COUNT(*) AS total_items
                  FROM assignment_checklist_items
                  WHERE weekly_assignment_id = (
                    SELECT id FROM current_assignment
                  )
                ),
                completion_counts AS (
                  SELECT completion.completion_date,
                         SUM(completion.is_completed) AS completed_items,
                         COUNT(*) AS recorded_items
                  FROM assignment_checklist_items AS item
                  JOIN daily_checklist_completions AS completion
                    ON completion.assignment_checklist_item_id = item.id
                  WHERE item.weekly_assignment_id = (
                    SELECT id FROM current_assignment
                  )
                  GROUP BY completion.completion_date
                )
                SELECT week_days.day,
                       COALESCE(items.total_items, 0) AS total_items,
                       COALESCE(completion.completed_items, 0)
                         AS completed_items,
                       COALESCE(completion.recorded_items, 0)
                         AS recorded_items,
                       CASE
                         WHEN COALESCE(completion.recorded_items, 0) = 0
                         THEN 'not_recorded'
                         WHEN COALESCE(items.total_items, 0) > 0
                          AND completion.completed_items = items.total_items
                         THEN 'complete'
                         ELSE 'incomplete'
                       END AS state
                FROM week_days
                LEFT JOIN item_counts AS items ON 1 = 1
                LEFT JOIN completion_counts AS completion
                  ON completion.completion_date = week_days.day
                ORDER BY week_days.day
                """,
                {
                    "family_member_id": family_member_id,
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                },
            ).fetchall()
            return {
                "selected": dict(selected_row),
                "members": [dict(row) for row in member_rows],
                "current_week_days": [dict(row) for row in week_rows],
            }

    def get_completion_history(self, family_member_id, limit, offset):
        with transaction(self._database_path) as connection:
            member = connection.execute(
                "SELECT id FROM family_members WHERE id = ?", (family_member_id,)
            ).fetchone()
            if member is None:
                return None
            total = connection.execute(
                """SELECT COUNT(*) * 7 FROM weekly_assignments
                   WHERE family_member_id = ?""",
                (family_member_id,),
            ).fetchone()[0]
            rows = connection.execute(
                """
                WITH RECURSIVE assignment_days AS (
                  SELECT a.id AS assignment_id, a.week_start, a.week_end,
                         a.chore_name_snapshot, a.chore_description_snapshot,
                         a.week_start AS completion_date
                  FROM weekly_assignments AS a WHERE a.family_member_id = ?
                  UNION ALL
                  SELECT assignment_id, week_start, week_end, chore_name_snapshot,
                         chore_description_snapshot, date(completion_date, '+1 day')
                  FROM assignment_days WHERE completion_date < week_end
                ),
                checklist_counts AS (
                  SELECT weekly_assignment_id, COUNT(*) AS item_count
                  FROM assignment_checklist_items GROUP BY weekly_assignment_id
                ),
                daily_completion_counts AS (
                  SELECT item.weekly_assignment_id, completion.completion_date,
                         COUNT(*) AS recorded_count,
                         SUM(completion.is_completed) AS completed_count
                  FROM assignment_checklist_items AS item
                  JOIN daily_checklist_completions AS completion
                    ON completion.assignment_checklist_item_id = item.id
                  GROUP BY item.weekly_assignment_id, completion.completion_date
                )
                SELECT day.assignment_id, day.week_start, day.week_end,
                       day.chore_name_snapshot, day.chore_description_snapshot,
                       day.completion_date,
                       CASE
                         WHEN COALESCE(checklist.item_count, 0) = 0
                           OR COALESCE(daily.recorded_count, 0) = 0
                           THEN 'not_yet_recorded'
                         WHEN daily.completed_count = checklist.item_count
                           THEN 'complete'
                         ELSE 'incomplete'
                       END AS completion_status
                FROM assignment_days AS day
                LEFT JOIN checklist_counts AS checklist
                  ON checklist.weekly_assignment_id = day.assignment_id
                LEFT JOIN daily_completion_counts AS daily
                  ON daily.weekly_assignment_id = day.assignment_id
                 AND daily.completion_date = day.completion_date
                ORDER BY day.completion_date DESC, day.assignment_id DESC
                LIMIT ? OFFSET ?
                """,
                (family_member_id, limit, offset),
            ).fetchall()
            return {
                "items": [
                    {
                        "assignment_id": row["assignment_id"],
                        "week_start": row["week_start"],
                        "week_end": row["week_end"],
                        "chore_name": row["chore_name_snapshot"],
                        "chore_description": row["chore_description_snapshot"],
                        "completion_date": row["completion_date"],
                        "completion_status": row["completion_status"],
                    }
                    for row in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
