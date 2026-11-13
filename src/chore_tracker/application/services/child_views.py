"""Application use cases for unauthenticated child-facing views."""

from __future__ import annotations

from datetime import date
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

    def get_completion_history(
        self, family_member_id: int, limit: int, offset: int
    ) -> dict[str, Any]:
        result = self._persistence.get_completion_history(
            family_member_id, limit, offset
        )
        if result is None:
            raise FamilyMemberNotFound
        return result
