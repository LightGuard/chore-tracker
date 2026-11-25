"""Application use cases for unauthenticated child-facing views."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class ChildViewError(Exception):
    """Application error translated by the HTTP adapter."""

    status_code = 500
    detail = "The child view request could not be completed."


class FamilyMemberNotFound(ChildViewError):
    status_code = 404
    detail = "Family member was not found"


class FamilyMemberInactive(ChildViewError):
    status_code = 409
    detail = "Family member is inactive"


class WeeklyAssignmentNotFound(ChildViewError):
    status_code = 404
    detail = "Weekly assignment was not found"


class CurrentAssignmentNotFound(ChildViewError):
    status_code = 404
    detail = "No weekly assignment exists for this family member"


class CompletionDateOutsideAssignment(ChildViewError):
    status_code = 422
    detail = "Completion date must be within the weekly assignment"


class ChecklistItemNotFound(ChildViewError):
    status_code = 404
    detail = "Checklist item was not found in the weekly assignment"


class ChildViewsService:
    """Coordinate child-facing read and completion use cases."""

    def __init__(self, persistence: Any) -> None:
        self._persistence = persistence

    def list_active_family_members(self) -> list[dict[str, Any]]:
        return self._persistence.list_active_family_members()

    def get_current_assignment(
        self, family_member_id: int, today: date
    ) -> dict[str, Any]:
        result = self._persistence.get_current_assignment(family_member_id, today)
        if result is None:
            raise FamilyMemberNotFound
        if result.get("inactive"):
            raise FamilyMemberInactive
        if result.get("assignment_missing"):
            raise CurrentAssignmentNotFound
        return result

    def get_assignment_completion(
        self, family_member_id: int, assignment_id: int, completion_date: date
    ) -> dict[str, Any]:
        result = self._persistence.get_assignment_completion(
            family_member_id, assignment_id, completion_date
        )
        if result is None:
            raise FamilyMemberNotFound
        if result.get("inactive"):
            raise FamilyMemberInactive
        if result.get("assignment_missing"):
            raise WeeklyAssignmentNotFound
        if result.get("date_outside_assignment"):
            raise CompletionDateOutsideAssignment
        return result["completion"]

    def update_assignment_checklist_completion(
        self,
        family_member_id: int,
        assignment_id: int,
        checklist_item_id: int,
        completion_date: date,
        is_completed: bool,
    ) -> dict[str, Any]:
        result = self._persistence.update_assignment_checklist_completion(
            family_member_id,
            assignment_id,
            checklist_item_id,
            completion_date,
            is_completed,
        )
        if result is None:
            raise FamilyMemberNotFound
        if result.get("inactive"):
            raise FamilyMemberInactive
        if result.get("assignment_missing"):
            raise WeeklyAssignmentNotFound
        if result.get("date_outside_assignment"):
            raise CompletionDateOutsideAssignment
        if result.get("item_missing"):
            raise ChecklistItemNotFound
        return result["completion"]

    def get_derived_stats(
        self, family_member_id: int, today: date, timezone_name: str
    ) -> dict[str, Any]:
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        result = self._persistence.get_derived_stats(
            family_member_id, today, week_start, week_end
        )
        if result is None:
            raise FamilyMemberNotFound
        selected = result["selected"]
        if not selected["is_active"]:
            raise FamilyMemberInactive

        active_members = [member for member in result["members"] if member["is_active"]]
        active_members.sort(
            key=lambda member: (
                -member["current_week_completed_items"],
                -member["current_streak"],
                member["display_name"].casefold(),
                member["family_member_id"],
            )
        )
        week_days = [
            {
                "date": row["day"],
                "completed_checklist_items": row["completed_items"],
                "total_checklist_items": row["total_items"],
                "state": row["state"],
            }
            for row in result["current_week_days"]
        ]
        return {
            "family_member_id": selected["family_member_id"],
            "display_name": selected["display_name"],
            "as_of": today.isoformat(),
            "timezone": timezone_name,
            "lifetime": {
                "completed_checklist_items": selected["lifetime_completed_items"],
                "complete_days": selected["lifetime_complete_days"],
                "current_streak": selected["current_streak"],
            },
            "current_week": {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "completed_checklist_items": selected["current_week_completed_items"],
                "complete_days": selected["current_week_complete_days"],
                "days": week_days,
            },
            "household": {
                "active_players": len(active_members),
                "weekly_standings": [
                    {
                        "family_member_id": member["family_member_id"],
                        "display_name": member["display_name"],
                        "completed_checklist_items": member[
                            "current_week_completed_items"
                        ],
                        "complete_days": member["current_week_complete_days"],
                        "current_streak": member["current_streak"],
                    }
                    for member in active_members
                ],
            },
        }

    def get_completion_history(
        self, family_member_id: int, limit: int, offset: int, today: date
    ) -> dict[str, Any]:
        result = self._persistence.get_completion_history(
            family_member_id, limit, offset, today
        )
        if result is None:
            raise FamilyMemberNotFound
        return result
