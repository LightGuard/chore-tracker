"""Application operations for per-day checklist completion."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException


def _assignment_for_member_and_date(
    connection: sqlite3.Connection,
    family_member_id: int,
    assignment_id: int,
    completion_date: date,
) -> sqlite3.Row:
    member = connection.execute(
        "SELECT is_active FROM family_members WHERE id = ?",
        (family_member_id,),
    ).fetchone()
    if member is None:
        raise HTTPException(status_code=404, detail="Family member was not found")
    if not member["is_active"]:
        raise HTTPException(status_code=409, detail="Family member is inactive")

    assignment = connection.execute(
        """SELECT id, week_start, week_end
           FROM weekly_assignments
           WHERE id = ? AND family_member_id = ?""",
        (assignment_id, family_member_id),
    ).fetchone()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Weekly assignment was not found")

    date_value = completion_date.isoformat()
    if not assignment["week_start"] <= date_value <= assignment["week_end"]:
        raise HTTPException(
            status_code=422,
            detail="Completion date must be within the weekly assignment",
        )
    return assignment


def get_daily_completion(
    connection: sqlite3.Connection,
    family_member_id: int,
    assignment_id: int,
    completion_date: date,
) -> dict[str, Any]:
    """Read one date's checklist state without creating completion records."""
    _assignment_for_member_and_date(
        connection, family_member_id, assignment_id, completion_date
    )
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
        "completion_date": completion_date,
        "checklist_items": items,
        "is_complete": bool(items) and all(item["is_completed"] for item in items),
    }


def set_checklist_item_completion(
    connection: sqlite3.Connection,
    family_member_id: int,
    assignment_id: int,
    checklist_item_id: int,
    completion_date: date,
    is_completed: bool,
) -> dict[str, Any]:
    """Idempotently set one checklist item's state for one local calendar date."""
    _assignment_for_member_and_date(
        connection, family_member_id, assignment_id, completion_date
    )
    item = connection.execute(
        """SELECT id FROM assignment_checklist_items
           WHERE id = ? AND weekly_assignment_id = ?""",
        (checklist_item_id, assignment_id),
    ).fetchone()
    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Checklist item was not found in the weekly assignment",
        )

    completed_at = (
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        if is_completed
        else None
    )
    connection.execute(
        """INSERT INTO daily_checklist_completions
           (assignment_checklist_item_id, completion_date, is_completed, completed_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (assignment_checklist_item_id, completion_date)
           DO UPDATE SET is_completed = excluded.is_completed,
                         completed_at = CASE
                             WHEN daily_checklist_completions.is_completed
                                  = excluded.is_completed
                             THEN daily_checklist_completions.completed_at
                             ELSE excluded.completed_at
                         END""",
        (
            checklist_item_id,
            completion_date.isoformat(),
            int(is_completed),
            completed_at,
        ),
    )
    daily_state = get_daily_completion(
        connection, family_member_id, assignment_id, completion_date
    )
    updated_item = next(
        item
        for item in daily_state["checklist_items"]
        if item["id"] == checklist_item_id
    )
    return {
        "assignment_id": assignment_id,
        "completion_date": completion_date,
        "checklist_item": updated_item,
        "is_complete": daily_state["is_complete"],
    }
