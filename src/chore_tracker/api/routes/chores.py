"""Administrator-protected chore catalog and checklist management endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.api.routes.auth import require_admin, require_same_origin
from chore_tracker.config import get_settings

router = APIRouter(prefix="/chores", tags=["chore management"])
Admin = Annotated[dict[str, Any], Depends(require_admin)]
SameOrigin = Annotated[None, Depends(require_same_origin)]


class ChoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    is_active: bool = False


class ChoreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ChecklistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=500)


class ChecklistItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, min_length=1, max_length=500)
    is_active: bool | None = None


class ChecklistOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordered_item_ids: list[int] = Field(min_length=1)


def _clean(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field} must not be blank")
    return cleaned


def _chore(connection, chore_id: int):
    row = connection.execute(
        "SELECT id, name, description, is_active, created_at, updated_at "
        "FROM chores WHERE id = ?",
        (chore_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Chore was not found")
    return row


def _item(connection, chore_id: int, item_id: int):
    row = connection.execute(
        """SELECT id, chore_id, label, position, is_active, created_at, updated_at
           FROM chore_checklist_items WHERE id = ? AND chore_id = ?""",
        (item_id, chore_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Checklist item was not found")
    return row


def _active_item_count(connection, chore_id: int) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM chore_checklist_items "
        "WHERE chore_id = ? AND is_active = 1",
        (chore_id,),
    ).fetchone()[0]


def _serialize_chore(connection, chore_id: int) -> dict[str, Any]:
    chore = _chore(connection, chore_id)
    items = connection.execute(
        """SELECT id, label, position, is_active, created_at, updated_at
           FROM chore_checklist_items WHERE chore_id = ?
           ORDER BY position, id""",
        (chore_id,),
    ).fetchall()
    return {
        **dict(chore),
        "is_active": bool(chore["is_active"]),
        "checklist_items": [
            {**dict(item), "is_active": bool(item["is_active"])} for item in items
        ],
    }


@router.get("")
def list_chores(administrator: Admin) -> list[dict[str, Any]]:
    with transaction(get_settings().database_path) as connection:
        ids = connection.execute(
            "SELECT id FROM chores ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [_serialize_chore(connection, row["id"]) for row in ids]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_chore(request: ChoreCreate, administrator: Admin, origin: SameOrigin):
    name = _clean(request.name, "Name")
    with transaction(get_settings().database_path) as connection:
        if request.is_active:
            raise HTTPException(
                status_code=422,
                detail=(
                    "A chore must have an active checklist item "
                    "before it can be activated"
                ),
            )
        chore_id = connection.execute(
            "INSERT INTO chores (name, description, is_active) VALUES (?, ?, 0)",
            (name, request.description.strip()),
        ).lastrowid
        return _serialize_chore(connection, chore_id)


@router.get("/{chore_id}")
def get_chore(chore_id: int, administrator: Admin):
    with transaction(get_settings().database_path) as connection:
        return _serialize_chore(connection, chore_id)


@router.patch("/{chore_id}")
def update_chore(
    chore_id: int, request: ChoreUpdate, administrator: Admin, origin: SameOrigin
):
    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one field is required")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Fields cannot be null")
    if "name" in changes and changes["name"] is not None:
        changes["name"] = _clean(changes["name"], "Name")
    if "description" in changes and changes["description"] is not None:
        changes["description"] = changes["description"].strip()
    with transaction(get_settings().database_path) as connection:
        _chore(connection, chore_id)
        if (
            changes.get("is_active") is True
            and _active_item_count(connection, chore_id) == 0
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "A chore needs at least one active checklist item "
                    "before activation"
                ),
            )
        assignments = ", ".join(f"{field} = ?" for field in changes)
        if changes:
            connection.execute(
                f"UPDATE chores SET {assignments}, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                (*changes.values(), chore_id),
            )
        return _serialize_chore(connection, chore_id)


@router.post("/{chore_id}/checklist-items", status_code=status.HTTP_201_CREATED)
def add_checklist_item(
    chore_id: int,
    request: ChecklistItemCreate,
    administrator: Admin,
    origin: SameOrigin,
):
    label = _clean(request.label, "Checklist label")
    with transaction(get_settings().database_path) as connection:
        _chore(connection, chore_id)
        position = connection.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM chore_checklist_items "
            "WHERE chore_id = ?",
            (chore_id,),
        ).fetchone()[0]
        item_id = connection.execute(
            "INSERT INTO chore_checklist_items "
            "(chore_id, label, position) VALUES (?, ?, ?)",
            (chore_id, label, position),
        ).lastrowid
        item = _item(connection, chore_id, item_id)
        return {**dict(item), "is_active": bool(item["is_active"])}


@router.patch("/{chore_id}/checklist-items/{item_id}")
def update_checklist_item(
    chore_id: int,
    item_id: int,
    request: ChecklistItemUpdate,
    administrator: Admin,
    origin: SameOrigin,
):
    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one field is required")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Fields cannot be null")
    if "label" in changes and changes["label"] is not None:
        changes["label"] = _clean(changes["label"], "Checklist label")
    with transaction(get_settings().database_path) as connection:
        _chore(connection, chore_id)
        current = _item(connection, chore_id, item_id)
        if current["is_active"] and changes.get("is_active") is False:
            if (
                _chore(connection, chore_id)["is_active"]
                and _active_item_count(connection, chore_id) <= 1
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Deactivate the chore before removing its last "
                        "active checklist item"
                    ),
                )
        assignments = ", ".join(f"{field} = ?" for field in changes)
        connection.execute(
            f"UPDATE chore_checklist_items SET {assignments}, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (*changes.values(), item_id),
        )
        item = _item(connection, chore_id, item_id)
        return {**dict(item), "is_active": bool(item["is_active"])}


@router.delete(
    "/{chore_id}/checklist-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_checklist_item(
    chore_id: int, item_id: int, administrator: Admin, origin: SameOrigin
):
    with transaction(get_settings().database_path) as connection:
        chore = _chore(connection, chore_id)
        _item(connection, chore_id, item_id)
        item = connection.execute(
            "SELECT is_active FROM chore_checklist_items WHERE id = ?", (item_id,)
        ).fetchone()
        if (
            chore["is_active"]
            and item["is_active"]
            and _active_item_count(connection, chore_id) <= 1
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Deactivate the chore before removing its last "
                    "active checklist item"
                ),
            )
        connection.execute("DELETE FROM chore_checklist_items WHERE id = ?", (item_id,))
    return None


@router.put("/{chore_id}/checklist-order")
def reorder_checklist(
    chore_id: int, request: ChecklistOrder, administrator: Admin, origin: SameOrigin
):
    if len(set(request.ordered_item_ids)) != len(request.ordered_item_ids):
        raise HTTPException(status_code=422, detail="Checklist item IDs must be unique")
    with transaction(get_settings().database_path) as connection:
        _chore(connection, chore_id)
        existing = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM chore_checklist_items "
                "WHERE chore_id = ? ORDER BY position",
                (chore_id,),
            ).fetchall()
        ]
        if set(existing) != set(request.ordered_item_ids) or len(existing) != len(
            request.ordered_item_ids
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "The order must contain every checklist item "
                    "for this chore exactly once"
                ),
            )
        # Move positions above the current range before assigning the new order;
        # the schema requires non-negative positions and enforces uniqueness.
        offset = max(existing, default=-1) + len(existing) + 1
        connection.execute(
            "UPDATE chore_checklist_items SET position = position + ? "
            "WHERE chore_id = ?",
            (offset, chore_id),
        )
        for position, item_id in enumerate(request.ordered_item_ids):
            connection.execute(
                """UPDATE chore_checklist_items SET position = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?""",
                (position, item_id),
            )
        return _serialize_chore(connection, chore_id)
