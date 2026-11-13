"""Application use cases for per-day checklist completion."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class CompletionError(Exception):
    """Application error translated by the HTTP adapter."""

    status_code = 500
    detail = "The completion request could not be completed."


class FamilyMemberNotFound(CompletionError):
    status_code = 404
    detail = "Family member was not found"


class FamilyMemberInactive(CompletionError):
    status_code = 409
    detail = "Family member is inactive"


class WeeklyAssignmentNotFound(CompletionError):
    status_code = 404
    detail = "Weekly assignment was not found"


class CompletionDateOutsideAssignment(CompletionError):
    status_code = 422
    detail = "Completion date must be within the weekly assignment"


class ChecklistItemNotFound(CompletionError):
    status_code = 404
    detail = "Checklist item was not found in the weekly assignment"


class CompletionPersistence(Protocol):
    def get_daily_completion(self, family_member_id: int, assignment_id: int, completion_date: date) -> dict[str, Any]: ...
    def set_checklist_item_completion(self, family_member_id: int, assignment_id: int, checklist_item_id: int, completion_date: date, is_completed: bool) -> dict[str, Any]: ...


class CompletionService:
    """Coordinate completion use cases without depending on storage details."""

    def __init__(self, persistence: CompletionPersistence) -> None:
        self._persistence = persistence

    def get_daily_completion(self, family_member_id: int, assignment_id: int, completion_date: date) -> dict[str, Any]:
        return self._persistence.get_daily_completion(family_member_id, assignment_id, completion_date)

    def set_checklist_item_completion(self, family_member_id: int, assignment_id: int, checklist_item_id: int, completion_date: date, is_completed: bool) -> dict[str, Any]:
        return self._persistence.set_checklist_item_completion(family_member_id, assignment_id, checklist_item_id, completion_date, is_completed)
