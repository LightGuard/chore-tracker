"""Application use case for historical daily completion queries."""

from __future__ import annotations

from typing import Any, Protocol


class CompletionHistoryPersistence(Protocol):
    def get_completion_history(self, family_member_id: int, limit: int, offset: int) -> dict[str, Any] | None: ...


class FamilyMemberNotFound(Exception):
    """Raised when the requested family member does not exist."""

    status_code = 404
    detail = "Family member was not found"


class CompletionHistoryService:
    """Coordinate historical completion queries through a persistence port."""

    def __init__(self, persistence: CompletionHistoryPersistence) -> None:
        self._persistence = persistence

    def get_completion_history(self, family_member_id: int, limit: int, offset: int) -> dict[str, Any]:
        result = self._persistence.get_completion_history(family_member_id, limit, offset)
        if result is None:
            raise FamilyMemberNotFound
        return result
