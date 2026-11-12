"""Administrator-protected family member profile management endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.api.routes.auth import require_admin, require_same_origin
from chore_tracker.config import get_settings

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


def _clean_display_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Display name must not be blank",
        )
    if len(cleaned) > DISPLAY_NAME_MAX_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Display name must be at most {DISPLAY_NAME_MAX_LENGTH} characters",
        )
    return cleaned


def _family_member(connection, family_member_id: int):
    row = connection.execute(
        """SELECT id, display_name, is_active, created_at, updated_at
           FROM family_members WHERE id = ?""",
        (family_member_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Family member was not found")
    return {**dict(row), "is_active": bool(row["is_active"])}


@router.get("")
def list_family_members(administrator: Admin) -> list[dict[str, Any]]:
    """List all profiles, including inactive profiles, for administrator management."""
    with transaction(get_settings().database_path) as connection:
        rows = connection.execute(
            """SELECT id, display_name, is_active, created_at, updated_at
               FROM family_members
               ORDER BY display_name COLLATE NOCASE, id"""
        ).fetchall()
        return [{**dict(row), "is_active": bool(row["is_active"])} for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_family_member(
    request: FamilyMemberCreate, administrator: Admin, origin: SameOrigin
) -> dict[str, Any]:
    """Create a profile. Duplicate display names are permitted."""
    display_name = _clean_display_name(request.display_name)
    with transaction(get_settings().database_path) as connection:
        family_member_id = connection.execute(
            """INSERT INTO family_members (display_name, is_active)
               VALUES (?, ?)""",
            (display_name, int(request.is_active)),
        ).lastrowid
        return _family_member(connection, family_member_id)


@router.get("/{family_member_id}")
def get_family_member(family_member_id: int, administrator: Admin) -> dict[str, Any]:
    with transaction(get_settings().database_path) as connection:
        return _family_member(connection, family_member_id)


@router.patch("/{family_member_id}")
def update_family_member(
    family_member_id: int,
    request: FamilyMemberUpdate,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one field is required")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Fields cannot be null")
    if "display_name" in changes:
        changes["display_name"] = _clean_display_name(changes["display_name"])

    with transaction(get_settings().database_path) as connection:
        _family_member(connection, family_member_id)
        assignments = ", ".join(f"{field} = ?" for field in changes)
        connection.execute(
            f"""UPDATE family_members SET {assignments},
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?""",
            (*changes.values(), family_member_id),
        )
        return _family_member(connection, family_member_id)
