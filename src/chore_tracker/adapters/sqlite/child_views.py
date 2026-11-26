"""SQLite persistence for child-facing views and completion operations."""

from __future__ import annotations

import sqlite3
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
                          chore_name_snapshot, chore_description_snapshot,
                          chore_weight_snapshot
                   FROM weekly_assignments
                   WHERE family_member_id = ? AND week_start = ?""",
                (family_member_id, week_start.isoformat()),
            ).fetchone()
            if assignment is None:
                return {"assignment_missing": True}
            rows = connection.execute(
                """SELECT snapshot.id, snapshot.label_snapshot, snapshot.position,
                          snapshot.is_required,
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
                    "is_required": bool(row["is_required"]),
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
                "chore_weight": assignment["chore_weight_snapshot"],
                "today": today,
                "checklist_items": items,
                "is_complete": bool(items)
                and all(item["is_completed"] for item in items if item["is_required"]),
            }

    @staticmethod
    def _member_status(connection, family_member_id: int) -> str | None:
        member = connection.execute(
            "SELECT is_active FROM family_members WHERE id = ?",
            (family_member_id,),
        ).fetchone()
        if member is None:
            return None
        return "active" if member["is_active"] else "inactive"

    @staticmethod
    def _claim(row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "family_member_id": row["family_member_id"],
            "chore_id": row["chore_id"],
            "claim_date": date.fromisoformat(row["claim_date"]),
            "week_start": date.fromisoformat(row["week_start"]),
            "week_end": date.fromisoformat(row["week_end"]),
            "chore_name": row["chore_name_snapshot"],
            "chore_description": row["chore_description_snapshot"],
            "chore_weight": row["chore_weight_snapshot"],
            "claimed_at": row["claimed_at"],
            "is_completed": bool(row["is_completed"]),
        }

    @staticmethod
    def _claim_select() -> str:
        """Columns for a claim joined to its day-specific done state."""
        return """SELECT claim.id, claim.family_member_id, claim.chore_id,
                         claim.claim_date, claim.week_start, claim.week_end,
                         claim.chore_name_snapshot,
                         claim.chore_description_snapshot,
                         claim.chore_weight_snapshot, claim.claimed_at,
                         COALESCE(completion.is_completed, 0) AS is_completed
                  FROM daily_chore_claims AS claim
                  LEFT JOIN daily_chore_claim_completions AS completion
                    ON completion.claim_id = claim.id"""

    # A weekly-assigned chore counts as "done today" when it has checklist
    # items and every required item has a completed completion row for the day.
    # This mirrors the is_complete rule used by the child's current assignment.
    _CHORE_NOT_DONE_SQL = """
        (
          (SELECT COUNT(*) FROM assignment_checklist_items AS item
           WHERE item.weekly_assignment_id = assignment.id) = 0
          OR EXISTS (
            SELECT 1 FROM assignment_checklist_items AS item
            LEFT JOIN daily_checklist_completions AS completion
              ON completion.assignment_checklist_item_id = item.id
             AND completion.completion_date = :day
            WHERE item.weekly_assignment_id = assignment.id
              AND item.is_required = 1
              AND COALESCE(completion.is_completed, 0) = 0
          )
        )
    """

    def list_claimable_chores(
        self, family_member_id: int, day: date, after_takeover_hour: bool
    ) -> dict[str, Any] | None:
        """Return chores a child can claim for one local date.

        Unassigned active chores are always available. After 20:00 local time,
        chores assigned to another active child that are not done today also
        become available as one-day takeovers.
        """
        week_start = day - timedelta(days=day.weekday())
        with transaction(self._database_path) as connection:
            status = self._member_status(connection, family_member_id)
            if status is None:
                return None
            if status == "inactive":
                return {"inactive": True}
            rows = connection.execute(
                f"""SELECT * FROM (
                      SELECT chore.id, chore.name, chore.description,
                             chore.weight, NULL AS assigned_to
                      FROM chores AS chore
                      WHERE chore.is_active = 1
                        AND NOT EXISTS (
                          SELECT 1 FROM weekly_assignments AS assignment
                          WHERE assignment.chore_id = chore.id
                            AND assignment.week_start = :week_start
                        )
                        AND NOT EXISTS (
                          SELECT 1 FROM daily_chore_claims AS claim
                          WHERE claim.chore_id = chore.id
                            AND claim.claim_date = :day
                        )
                      UNION ALL
                      SELECT chore.id, chore.name, chore.description,
                             chore.weight, member.display_name AS assigned_to
                      FROM chores AS chore
                      JOIN weekly_assignments AS assignment
                        ON assignment.chore_id = chore.id
                      JOIN family_members AS member
                        ON member.id = assignment.family_member_id
                      WHERE :after_20 = 1
                        AND chore.is_active = 1
                        AND assignment.week_start = :week_start
                        AND assignment.family_member_id != :family_member_id
                        AND member.is_active = 1
                        AND NOT EXISTS (
                          SELECT 1 FROM daily_chore_claims AS claim
                          WHERE claim.chore_id = chore.id
                            AND claim.claim_date = :day
                        )
                        AND {self._CHORE_NOT_DONE_SQL}
                    ) AS available
                    ORDER BY name COLLATE NOCASE, id""",
                {
                    "week_start": week_start.isoformat(),
                    "day": day.isoformat(),
                    "family_member_id": family_member_id,
                    "after_20": int(after_takeover_hour),
                },
            ).fetchall()
            chores = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "weight": row["weight"],
                    "assigned_to": row["assigned_to"],
                }
                for row in rows
            ]
            return {"claim_date": day, "chores": chores}

    def list_claimed_chores(
        self, family_member_id: int, day: date
    ) -> dict[str, Any] | None:
        """Return one date's one-day chore claims for one child."""
        with transaction(self._database_path) as connection:
            status = self._member_status(connection, family_member_id)
            if status is None:
                return None
            if status == "inactive":
                return {"inactive": True}
            rows = connection.execute(
                f"""{self._claim_select()}
                   WHERE claim.family_member_id = ? AND claim.claim_date = ?
                   ORDER BY claim.claimed_at, claim.id""",
                (family_member_id, day.isoformat()),
            ).fetchall()
            return {
                "claim_date": day,
                "claims": [self._claim(row) for row in rows],
            }

    def claim_chore(
        self,
        family_member_id: int,
        chore_id: int,
        day: date,
        after_takeover_hour: bool,
    ) -> dict[str, Any] | None:
        """Claim an unassigned chore, or take over an undone chore after 20:00.

        A chore weekly-assigned to another active child can be claimed after
        20:00 only while it is not done today. Either way the result is a single
        one-day claim; weekly assignments and rotation are never modified.
        """
        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=6)
        with transaction(self._database_path) as connection:
            # Serialize competing claims before checking availability.
            connection.execute("BEGIN IMMEDIATE")
            status = self._member_status(connection, family_member_id)
            if status is None:
                return None
            if status == "inactive":
                return {"inactive": True}
            chore = connection.execute(
                """SELECT name, description, weight, is_active
                   FROM chores WHERE id = ?""",
                (chore_id,),
            ).fetchone()
            if chore is None:
                return {"chore_missing": True}
            if not chore["is_active"]:
                return {"chore_inactive": True}
            assigned = connection.execute(
                """SELECT assignment.id, assignment.family_member_id,
                          member.is_active AS owner_active
                   FROM weekly_assignments AS assignment
                   JOIN family_members AS member
                     ON member.id = assignment.family_member_id
                   WHERE assignment.chore_id = ?
                     AND assignment.week_start = ?""",
                (chore_id, week_start.isoformat()),
            ).fetchone()
            takeover = (
                assigned is not None
                and after_takeover_hour
                and assigned["family_member_id"] != family_member_id
                and bool(assigned["owner_active"])
            )
            if assigned is not None and not takeover:
                return {"assignment_exists": True}
            if takeover:
                done = connection.execute(
                    f"""SELECT NOT {self._CHORE_NOT_DONE_SQL} AS is_done
                        FROM weekly_assignments AS assignment
                        WHERE assignment.id = :assignment_id""",
                    {"assignment_id": assigned["id"], "day": day.isoformat()},
                ).fetchone()["is_done"]
                if done:
                    return {"chore_already_done": True}
            existing = connection.execute(
                """SELECT 1 FROM daily_chore_claims
                   WHERE chore_id = ? AND claim_date = ?""",
                (chore_id, day.isoformat()),
            ).fetchone()
            if existing is not None:
                return {"claim_exists": True}
            try:
                claim_id = connection.execute(
                    """INSERT INTO daily_chore_claims
                       (family_member_id, chore_id, claim_date, week_start,
                        week_end, chore_name_snapshot,
                        chore_description_snapshot, chore_weight_snapshot)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        family_member_id,
                        chore_id,
                        day.isoformat(),
                        week_start.isoformat(),
                        week_end.isoformat(),
                        chore["name"],
                        chore["description"],
                        chore["weight"],
                    ),
                ).lastrowid
            except sqlite3.IntegrityError:
                raced = connection.execute(
                    """SELECT 1 FROM daily_chore_claims
                       WHERE chore_id = ? AND claim_date = ?""",
                    (chore_id, day.isoformat()),
                ).fetchone()
                if raced is not None:
                    return {"claim_exists": True}
                raise
            row = connection.execute(
                f"{self._claim_select()} WHERE claim.id = ?",
                (claim_id,),
            ).fetchone()
            return {"claim": self._claim(row)}

    def set_claim_completion(
        self,
        family_member_id: int,
        claim_id: int,
        is_completed: bool,
        day: date,
    ) -> dict[str, Any] | None:
        """Set the done state of one child's one-day claim for today."""
        with transaction(self._database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            status = self._member_status(connection, family_member_id)
            if status is None:
                return None
            if status == "inactive":
                return {"inactive": True}
            claim = connection.execute(
                """SELECT id, claim_date FROM daily_chore_claims
                   WHERE id = ? AND family_member_id = ?""",
                (claim_id, family_member_id),
            ).fetchone()
            if claim is None:
                return {"claim_missing": True}
            if claim["claim_date"] != day.isoformat():
                return {"stale_claim": True}
            completed_at = (
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                if is_completed
                else None
            )
            connection.execute(
                """INSERT INTO daily_chore_claim_completions
                   (claim_id, is_completed, completed_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT (claim_id) DO UPDATE SET
                     is_completed = excluded.is_completed,
                     completed_at = CASE
                       WHEN daily_chore_claim_completions.is_completed
                            = excluded.is_completed
                       THEN daily_chore_claim_completions.completed_at
                       ELSE excluded.completed_at END""",
                (claim_id, int(is_completed), completed_at),
            )
            row = connection.execute(
                f"{self._claim_select()} WHERE claim.id = ?",
                (claim_id,),
            ).fetchone()
            return {"claim": self._claim(row)}

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
                      snapshot.is_required,
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
                "is_required": bool(row["is_required"]),
                "is_completed": bool(row["is_completed"]),
            }
            for row in rows
        ]
        return {
            "assignment_id": assignment_id,
            "completion_date": day,
            "checklist_items": items,
            "is_complete": bool(items)
            and all(item["is_completed"] for item in items if item["is_required"]),
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
            # Once another child takes over this chore for the day, the
            # originally assigned child cannot also complete it: the day must
            # not be counted as complete for them, and the XP belongs to the
            # claimant alone.
            taken_over = connection.execute(
                """SELECT 1 FROM daily_chore_claims AS claim
                   JOIN weekly_assignments AS assignment
                     ON assignment.chore_id = claim.chore_id
                    AND assignment.week_start = claim.week_start
                   WHERE assignment.id = ?
                     AND claim.claim_date = ?
                     AND claim.family_member_id != ?""",
                (assignment_id, day.isoformat(), family_member_id),
            ).fetchone()
            if taken_over is not None:
                return {"chore_taken_over": True}
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
                required_item_counts AS (
                  SELECT item.weekly_assignment_id,
                         COUNT(*) AS required_items
                  FROM assignment_checklist_items AS item
                  WHERE item.is_required = 1
                    AND item.weekly_assignment_id IN (
                      SELECT assignment_id FROM assignment_days
                    )
                  GROUP BY item.weekly_assignment_id
                ),
                completion_counts AS (
                  SELECT item.weekly_assignment_id,
                         completion.completion_date,
                         SUM(completion.is_completed) AS completed_items,
                         SUM(
                           CASE WHEN completion.is_completed = 1
                                THEN assignment.chore_weight_snapshot
                                ELSE 0 END
                         ) AS completed_weight,
                         SUM(
                           CASE WHEN item.is_required = 1
                                     AND completion.is_completed = 1
                                THEN 1 ELSE 0 END
                         ) AS required_completed_items,
                         COUNT(*) AS recorded_items
                  FROM assignment_checklist_items AS item
                  JOIN daily_checklist_completions AS completion
                    ON completion.assignment_checklist_item_id = item.id
                  JOIN weekly_assignments AS assignment
                    ON assignment.id = item.weekly_assignment_id
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
                         COALESCE(required.required_items, 0) AS required_items,
                         COALESCE(completion.completed_items, 0)
                           AS completed_items,
                         COALESCE(completion.completed_weight, 0)
                           AS completed_weight,
                         COALESCE(completion.required_completed_items, 0)
                           AS required_completed_items,
                         CASE
                           WHEN COALESCE(items.total_items, 0) > 0
                            AND COALESCE(completion.required_completed_items, 0)
                                = COALESCE(required.required_items, 0)
                            AND (
                              COALESCE(required.required_items, 0) > 0
                              OR assignment_days.day <= :today
                            )
                           THEN 1
                           ELSE 0
                         END AS is_complete
                  FROM assignment_days
                  LEFT JOIN item_counts AS items
                    ON items.weekly_assignment_id
                       = assignment_days.assignment_id
                  LEFT JOIN required_item_counts AS required
                    ON required.weekly_assignment_id
                       = assignment_days.assignment_id
                  LEFT JOIN completion_counts AS completion
                    ON completion.weekly_assignment_id
                       = assignment_days.assignment_id
                   AND completion.completion_date = assignment_days.day
                ),
                claim_day_facts AS (
                  SELECT claim.family_member_id,
                         claim.claim_date AS day,
                         SUM(claim.chore_weight_snapshot) AS completed_weight
                  FROM daily_chore_claim_completions AS completion
                  JOIN daily_chore_claims AS claim
                    ON claim.id = completion.claim_id
                  WHERE completion.is_completed = 1
                  GROUP BY claim.family_member_id, claim.claim_date
                ),
                -- Claim completions add weighted XP items only. They do not
                -- count as checklist items, complete days, or streak days, and
                -- never reach completion history or weekly report snapshots.
                all_day_facts AS (
                  SELECT family_member_id, day, completed_items,
                         completed_weight, is_complete
                  FROM day_facts
                  UNION ALL
                  SELECT family_member_id, day, 0 AS completed_items,
                         completed_weight, 0 AS is_complete
                  FROM claim_day_facts
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
                           THEN fact.completed_weight
                           ELSE 0
                         END
                       ), 0) AS current_week_weighted_items,
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
                       COALESCE(SUM(fact.completed_weight), 0)
                         AS lifetime_weighted_items,
                       COALESCE(SUM(fact.is_complete), 0)
                         AS lifetime_complete_days,
                       COALESCE(streak.current_streak, 0)
                         AS current_streak
                FROM member_scope AS scope
                LEFT JOIN all_day_facts AS fact
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
                  SELECT COUNT(*) AS total_items,
                         SUM(CASE WHEN is_required = 1 THEN 1 ELSE 0 END)
                           AS required_items
                  FROM assignment_checklist_items
                  WHERE weekly_assignment_id = (
                    SELECT id FROM current_assignment
                  )
                ),
                completion_counts AS (
                  SELECT completion.completion_date,
                         SUM(completion.is_completed) AS completed_items,
                         SUM(
                           CASE WHEN item.is_required = 1
                                     AND completion.is_completed = 1
                                THEN 1 ELSE 0 END
                         ) AS required_completed_items,
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
                         WHEN COALESCE(items.total_items, 0) > 0
                          AND COALESCE(
                            completion.required_completed_items, 0
                          ) = COALESCE(items.required_items, 0)
                          AND (
                            COALESCE(items.required_items, 0) > 0
                            OR week_days.day <= date(:today)
                          )
                         THEN 'complete'
                         WHEN COALESCE(completion.recorded_items, 0) = 0
                         THEN 'not_recorded'
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
                    "today": today.isoformat(),
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                },
            ).fetchall()
            return {
                "selected": dict(selected_row),
                "members": [dict(row) for row in member_rows],
                "current_week_days": [dict(row) for row in week_rows],
            }

    def get_completion_history(self, family_member_id, limit, offset, today):
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
                         a.chore_weight_snapshot,
                         a.week_start AS completion_date
                  FROM weekly_assignments AS a WHERE a.family_member_id = ?
                  UNION ALL
                  SELECT assignment_id, week_start, week_end, chore_name_snapshot,
                         chore_description_snapshot, chore_weight_snapshot,
                         date(completion_date, '+1 day')
                  FROM assignment_days WHERE completion_date < week_end
                ),
                checklist_counts AS (
                  SELECT weekly_assignment_id,
                         COUNT(*) AS item_count,
                         SUM(CASE WHEN is_required = 1 THEN 1 ELSE 0 END)
                           AS required_item_count
                  FROM assignment_checklist_items GROUP BY weekly_assignment_id
                ),
                daily_completion_counts AS (
                  SELECT item.weekly_assignment_id, completion.completion_date,
                         COUNT(*) AS recorded_count,
                         SUM(
                           CASE WHEN item.is_required = 1
                                     AND completion.is_completed = 1
                                THEN 1 ELSE 0 END
                         ) AS required_completed_count
                  FROM assignment_checklist_items AS item
                  JOIN daily_checklist_completions AS completion
                    ON completion.assignment_checklist_item_id = item.id
                  GROUP BY item.weekly_assignment_id, completion.completion_date
                )
                SELECT day.assignment_id, day.week_start, day.week_end,
                       day.chore_name_snapshot, day.chore_description_snapshot,
                       day.chore_weight_snapshot, day.completion_date,
                       CASE
                         WHEN COALESCE(checklist.item_count, 0) = 0
                           THEN 'not_yet_recorded'
                         WHEN COALESCE(checklist.required_item_count, 0) = 0
                          AND day.completion_date <= ?
                           THEN 'complete'
                         WHEN COALESCE(checklist.required_item_count, 0) > 0
                          AND COALESCE(daily.required_completed_count, 0)
                              = checklist.required_item_count
                           THEN 'complete'
                         WHEN COALESCE(daily.recorded_count, 0) = 0
                           THEN 'not_yet_recorded'
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
                (family_member_id, today.isoformat(), limit, offset),
            ).fetchall()
            return {
                "items": [
                    {
                        "assignment_id": row["assignment_id"],
                        "week_start": row["week_start"],
                        "week_end": row["week_end"],
                        "chore_name": row["chore_name_snapshot"],
                        "chore_description": row["chore_description_snapshot"],
                        "chore_weight": row["chore_weight_snapshot"],
                        "completion_date": row["completion_date"],
                        "completion_status": row["completion_status"],
                    }
                    for row in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
