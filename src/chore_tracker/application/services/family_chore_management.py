"""Application use cases for family-member and chore management."""

from __future__ import annotations

from typing import Any, Protocol


class ManagementError(Exception):
    """A management use case could not be completed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ManagementPersistence(Protocol):
    def list_family_members(self) -> list[dict[str, Any]]: ...
    def create_family_member(self, display_name: str, is_active: bool) -> dict[str, Any]: ...
    def get_family_member(self, family_member_id: int) -> dict[str, Any] | None: ...
    def update_family_member(self, family_member_id: int, changes: dict[str, Any]) -> dict[str, Any] | None: ...
    def list_chores(self) -> list[dict[str, Any]]: ...
    def create_chore(self, name: str, description: str) -> dict[str, Any]: ...
    def get_chore(self, chore_id: int) -> dict[str, Any] | None: ...
    def update_chore(self, chore_id: int, changes: dict[str, Any]) -> dict[str, Any] | None: ...
    def add_checklist_item(self, chore_id: int, label: str) -> dict[str, Any] | None: ...
    def update_checklist_item(self, chore_id: int, item_id: int, changes: dict[str, Any]) -> dict[str, Any] | None: ...
    def delete_checklist_item(self, chore_id: int, item_id: int) -> str | None: ...
    def reorder_checklist(self, chore_id: int, ordered_item_ids: list[int]) -> dict[str, Any] | None: ...


class FamilyChoreManagementService:
    """Own management validation and use-case policy; delegate storage to a port."""

    def __init__(self, persistence: ManagementPersistence) -> None:
        self._persistence = persistence

    @staticmethod
    def _clean(value: str, field: str, maximum: int) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ManagementError("blank_value", f"{field} must not be blank")
        if len(cleaned) > maximum:
            raise ManagementError(
                "value_too_long", f"{field} must be at most {maximum} characters"
            )
        return cleaned

    @staticmethod
    def _changes(changes: dict[str, Any]) -> None:
        if not changes:
            raise ManagementError("empty_update", "At least one field is required")
        if any(value is None for value in changes.values()):
            raise ManagementError("null_field", "Fields cannot be null")

    def list_family_members(self) -> list[dict[str, Any]]:
        return self._persistence.list_family_members()

    def create_family_member(self, display_name: str, is_active: bool) -> dict[str, Any]:
        name = self._clean(display_name, "Display name", 100)
        return self._persistence.create_family_member(name, is_active)

    def get_family_member(self, family_member_id: int) -> dict[str, Any]:
        member = self._persistence.get_family_member(family_member_id)
        if member is None:
            raise ManagementError("family_member_missing", "Family member was not found")
        return member

    def update_family_member(self, family_member_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        self._changes(changes)
        if "display_name" in changes:
            changes["display_name"] = self._clean(changes["display_name"], "Display name", 100)
        member = self._persistence.update_family_member(family_member_id, changes)
        if member is None:
            raise ManagementError("family_member_missing", "Family member was not found")
        return member

    def list_chores(self) -> list[dict[str, Any]]:
        return self._persistence.list_chores()

    def create_chore(self, name: str, description: str, is_active: bool) -> dict[str, Any]:
        cleaned_name = self._clean(name, "Name", 200)
        if is_active:
            raise ManagementError(
                "chore_requires_checklist",
                "A chore must have an active checklist item before it can be activated",
            )
        return self._persistence.create_chore(cleaned_name, description.strip())

    def get_chore(self, chore_id: int) -> dict[str, Any]:
        chore = self._persistence.get_chore(chore_id)
        if chore is None:
            raise ManagementError("chore_missing", "Chore was not found")
        return chore

    def update_chore(self, chore_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        self._changes(changes)
        if "name" in changes:
            changes["name"] = self._clean(changes["name"], "Name", 200)
        if "description" in changes:
            changes["description"] = changes["description"].strip()
        chore = self._persistence.update_chore(chore_id, changes)
        if chore is None:
            raise ManagementError("chore_missing", "Chore was not found")
        if chore == {"conflict": "active_checklist_required"}:
            raise ManagementError(
                "active_checklist_required",
                "A chore needs at least one active checklist item before activation",
            )
        return chore

    def add_checklist_item(self, chore_id: int, label: str) -> dict[str, Any]:
        cleaned = self._clean(label, "Checklist label", 500)
        item = self._persistence.add_checklist_item(chore_id, cleaned)
        if item is None:
            raise ManagementError("chore_missing", "Chore was not found")
        return item

    def update_checklist_item(
        self, chore_id: int, item_id: int, changes: dict[str, Any]
    ) -> dict[str, Any]:
        self._changes(changes)
        if "label" in changes:
            changes["label"] = self._clean(changes["label"], "Checklist label", 500)
        item = self._persistence.update_checklist_item(chore_id, item_id, changes)
        if item is None or item == {"missing": "item"}:
            raise ManagementError("checklist_item_missing", "Checklist item was not found")
        if item == {"missing": "chore"}:
            raise ManagementError("chore_missing", "Chore was not found")
        if item == {"conflict": "last_active_item"}:
            raise ManagementError(
                "last_active_item",
                "Deactivate the chore before removing its last active checklist item",
            )
        return item

    def delete_checklist_item(self, chore_id: int, item_id: int) -> None:
        result = self._persistence.delete_checklist_item(chore_id, item_id)
        if result == "chore_missing":
            raise ManagementError("chore_missing", "Chore was not found")
        if result == "item_missing":
            raise ManagementError("checklist_item_missing", "Checklist item was not found")
        if result == "last_active_item":
            raise ManagementError(
                "last_active_item",
                "Deactivate the chore before removing its last active checklist item",
            )

    def reorder_checklist(self, chore_id: int, ordered_item_ids: list[int]) -> dict[str, Any]:
        if len(set(ordered_item_ids)) != len(ordered_item_ids):
            raise ManagementError(
                "duplicate_order_ids", "Checklist item IDs must be unique"
            )
        chore = self._persistence.reorder_checklist(chore_id, ordered_item_ids)
        if chore is None:
            raise ManagementError("chore_missing", "Chore was not found")
        if chore == {"invalid_order": True}:
            raise ManagementError(
                "invalid_order",
                "The order must contain every checklist item for this chore exactly once",
            )
        return chore
