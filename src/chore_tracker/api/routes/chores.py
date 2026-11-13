"""Administrator-protected chore catalog and checklist management endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from chore_tracker.api.routes.auth import require_admin, require_same_origin
from chore_tracker.application.services.family_chore_management import (
    FamilyChoreManagementService,
    ManagementError,
)

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


def _service(request: Request) -> FamilyChoreManagementService:
    return request.app.state.management_service_factory()


def _call(operation, *args):
    try:
        return operation(*args)
    except ManagementError as error:
        code_status = {
            "chore_missing": 404,
            "checklist_item_missing": 404,
            "blank_value": 422,
            "value_too_long": 422,
            "empty_update": 422,
            "null_field": 422,
            "duplicate_order_ids": 422,
            "invalid_order": 422,
            "chore_requires_checklist": 422,
            "active_checklist_required": 409,
            "last_active_item": 409,
        }
        raise HTTPException(
            status_code=code_status.get(error.code, 400), detail=str(error)
        ) from error


@router.get("")
def list_chores(request: Request, administrator: Admin) -> list[dict[str, Any]]:
    return _call(_service(request).list_chores)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_chore(
    body: ChoreCreate,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    return _call(
        _service(request).create_chore,
        body.name,
        body.description,
        body.is_active,
    )


@router.get("/{chore_id}")
def get_chore(
    chore_id: int, request: Request, administrator: Admin
) -> dict[str, Any]:
    return _call(_service(request).get_chore, chore_id)


@router.patch("/{chore_id}")
def update_chore(
    chore_id: int,
    body: ChoreUpdate,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    return _call(
        _service(request).update_chore,
        chore_id,
        body.model_dump(exclude_unset=True),
    )


@router.post(
    "/{chore_id}/checklist-items", status_code=status.HTTP_201_CREATED
)
def add_checklist_item(
    chore_id: int,
    body: ChecklistItemCreate,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    return _call(_service(request).add_checklist_item, chore_id, body.label)


@router.patch("/{chore_id}/checklist-items/{item_id}")
def update_checklist_item(
    chore_id: int,
    item_id: int,
    body: ChecklistItemUpdate,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    return _call(
        _service(request).update_checklist_item,
        chore_id,
        item_id,
        body.model_dump(exclude_unset=True),
    )


@router.delete(
    "/{chore_id}/checklist-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_checklist_item(
    chore_id: int,
    item_id: int,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> Response:
    _call(_service(request).delete_checklist_item, chore_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{chore_id}/checklist-order")
def reorder_checklist(
    chore_id: int,
    body: ChecklistOrder,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    return _call(
        _service(request).reorder_checklist, chore_id, body.ordered_item_ids
    )
