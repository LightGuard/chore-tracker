"""Unauthenticated child-facing family selection and current assignment endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.config import get_settings

router = APIRouter(prefix="/family-members", tags=["child views"])


class ActiveFamilyMember(BaseModel):
    """A profile available in the child-facing selector."""

    model_config = ConfigDict(extra="forbid")

    id: int
    display_name: str


class AssignmentChecklistItem(BaseModel):
    """One immutable checklist snapshot and its completion state for today."""

    model_config = ConfigDict(extra="forbid")

    id: int
    label: str
    position: int
    is_completed: bool


class CurrentWeeklyAssignment(BaseModel):
    """The selected child's current weekly chore and today's checklist state."""

    model_config = ConfigDict(extra="forbid")

    id: int
    family_member_id: int
    week_start: date
    week_end: date
    chore_name: str
    chore_description: str
    today: date
    checklist_items: list[AssignmentChecklistItem]
    is_complete: bool


def _today() -> date:
    """Return the current date in the configured household timezone."""
    timezone = ZoneInfo(get_settings().report_timezone)
    return datetime.now(timezone).date()


@router.get(
    "/active",
    response_model=list[ActiveFamilyMember],
    summary="List active family members for child selection",
)
def list_active_family_members() -> list[dict[str, Any]]:
    """Return only active profiles, ordered consistently for the selector."""
    with transaction(get_settings().database_path) as connection:
        rows = connection.execute(
            """SELECT id, display_name
               FROM family_members
               WHERE is_active = 1
               ORDER BY display_name COLLATE NOCASE, id"""
        ).fetchall()
        return [dict(row) for row in rows]


@router.get(
    "/{family_member_id}/current-assignment",
    response_model=CurrentWeeklyAssignment,
    responses={
        404: {"description": "Family member or current weekly assignment not found."},
        409: {"description": "The selected family member is inactive."},
    },
    summary="Get a child's current weekly chore",
)
def get_current_assignment(family_member_id: int) -> dict[str, Any]:
    """Return the immutable current-week assignment and today's completion state."""
    today = _today()
    week_start = today - timedelta(days=today.weekday())
    with transaction(get_settings().database_path) as connection:
        member = connection.execute(
            "SELECT is_active FROM family_members WHERE id = ?",
            (family_member_id,),
        ).fetchone()
        if member is None:
            raise HTTPException(status_code=404, detail="Family member was not found")
        if not member["is_active"]:
            raise HTTPException(status_code=409, detail="Family member is inactive")

        assignment = connection.execute(
            """SELECT id, family_member_id, week_start, week_end,
                      chore_name_snapshot, chore_description_snapshot
               FROM weekly_assignments
               WHERE family_member_id = ? AND week_start = ?""",
            (family_member_id, week_start.isoformat()),
        ).fetchone()
        if assignment is None:
            raise HTTPException(
                status_code=404,
                detail="No weekly assignment exists for this family member",
            )

        checklist_rows = connection.execute(
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
        checklist_items = [
            {
                "id": row["id"],
                "label": row["label_snapshot"],
                "position": row["position"],
                "is_completed": bool(row["is_completed"]),
            }
            for row in checklist_rows
        ]

        return {
            "id": assignment["id"],
            "family_member_id": assignment["family_member_id"],
            "week_start": assignment["week_start"],
            "week_end": assignment["week_end"],
            "chore_name": assignment["chore_name_snapshot"],
            "chore_description": assignment["chore_description_snapshot"],
            "today": today,
            "checklist_items": checklist_items,
            "is_complete": bool(checklist_items)
            and all(item["is_completed"] for item in checklist_items),
        }
