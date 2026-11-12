"""Read-only historical daily completion queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException


def get_completion_history(
    connection: sqlite3.Connection,
    family_member_id: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Return paginated daily records from immutable weekly assignment snapshots."""
    member = connection.execute(
        "SELECT id FROM family_members WHERE id = ?",
        (family_member_id,),
    ).fetchone()
    if member is None:
        raise HTTPException(status_code=404, detail="Family member was not found")

    total = connection.execute(
        "SELECT COUNT(*) * 7 FROM weekly_assignments WHERE family_member_id = ?",
        (family_member_id,),
    ).fetchone()[0]

    rows = connection.execute(
        """
        WITH RECURSIVE assignment_days AS (
            SELECT
                assignment.id AS assignment_id,
                assignment.week_start,
                assignment.week_end,
                assignment.chore_name_snapshot,
                assignment.chore_description_snapshot,
                assignment.week_start AS completion_date
            FROM weekly_assignments AS assignment
            WHERE assignment.family_member_id = ?

            UNION ALL

            SELECT
                assignment_id,
                week_start,
                week_end,
                chore_name_snapshot,
                chore_description_snapshot,
                date(completion_date, '+1 day')
            FROM assignment_days
            WHERE completion_date < week_end
        ),
        checklist_counts AS (
            SELECT weekly_assignment_id, COUNT(*) AS item_count
            FROM assignment_checklist_items
            GROUP BY weekly_assignment_id
        ),
        daily_completion_counts AS (
            SELECT
                item.weekly_assignment_id,
                completion.completion_date,
                COUNT(*) AS recorded_count,
                SUM(completion.is_completed) AS completed_count
            FROM assignment_checklist_items AS item
            JOIN daily_checklist_completions AS completion
              ON completion.assignment_checklist_item_id = item.id
            GROUP BY item.weekly_assignment_id, completion.completion_date
        )
        SELECT
            day.assignment_id,
            day.week_start,
            day.week_end,
            day.chore_name_snapshot,
            day.chore_description_snapshot,
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
