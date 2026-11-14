"""Administrator-protected family member profile management endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from chore_tracker.api.routes.auth import require_admin, require_same_origin
from chore_tracker.application.services.family_chore_management import (
    FamilyChoreManagementService,
    ManagementError,
)

router = APIRouter(prefix="/family-members", tags=["family member management"])
Admin = Annotated[dict[str, Any], Depends(require_admin)]
SameOrigin = Annotated[None, Depends(require_same_origin)]

DISPLAY_NAME_MAX_LENGTH = 100


class FamilyMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    is_active: bool = True


class FamilyMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(
        default=None, min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH
    )
    is_active: bool | None = None


def _service(request: Request) -> FamilyChoreManagementService:
    return request.app.state.management_service_factory()


def _call(operation, *args):
    try:
        return operation(*args)
    except ManagementError as error:
        code_status = {
            "family_member_missing": 404,
            "blank_value": 422,
            "value_too_long": 422,
            "empty_update": 422,
            "null_field": 422,
        }
        raise HTTPException(
            status_code=code_status.get(error.code, 400), detail=str(error)
        ) from error


@router.get("")
def list_family_members(request: Request, administrator: Admin) -> list[dict[str, Any]]:
    """List all profiles, including inactive profiles, for administrator management."""
    return _call(_service(request).list_family_members)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_family_member(
    body: FamilyMemberCreate,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    """Create a profile. Duplicate display names are permitted."""
    return _call(
        _service(request).create_family_member, body.display_name, body.is_active
    )


@router.get("/{family_member_id}")
def get_family_member(
    family_member_id: int, request: Request, administrator: Admin
) -> dict[str, Any]:
    return _call(_service(request).get_family_member, family_member_id)


@router.patch("/{family_member_id}")
def update_family_member(
    family_member_id: int,
    body: FamilyMemberUpdate,
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    return _call(
        _service(request).update_family_member,
        family_member_id,
        body.model_dump(exclude_unset=True),
    )
