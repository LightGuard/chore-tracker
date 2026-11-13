"""Unauthenticated child-facing family selection and assignment endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/family-members", tags=["child views"])

# Preserve the existing integration-test seam without making settings a route dependency.
globals()["get_settings"] = None


def _service(request: Request):
    settings_provider = globals().get("get_settings")
    if settings_provider is not None:
        return request.app.state.child_views_service_factory(settings_provider())
    return request.app.state.child_views_service


def _today(request: Request) -> date:
    settings_provider = globals().get("get_settings")
    if settings_provider is not None:
        return datetime.now(ZoneInfo(settings_provider().report_timezone)).date()
    return request.app.state.child_views_today()


def _invoke(operation):
    try:
        return operation()
    except Exception as error:
        if hasattr(error, "status_code") and hasattr(error, "detail"):
            raise HTTPException(
                status_code=error.status_code, detail=error.detail
            ) from error
        raise


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


@router.get(
    "/active",
    response_model=list[ActiveFamilyMember],
    summary="List active family members for child selection",
)
def list_active_family_members(request: Request) -> list[dict[str, Any]]:
    return _service(request).list_active_family_members()


@router.get(
    "/{family_member_id}/current-assignment",
    response_model=CurrentWeeklyAssignment,
    responses={
        404: {"description": "Family member or current weekly assignment not found."},
        409: {"description": "The selected family member is inactive."},
    },
    summary="Get a child's current weekly chore",
)
def get_current_assignment(family_member_id: int, request: Request) -> dict[str, Any]:
    return _invoke(
        lambda: _service(request).get_current_assignment(family_member_id, _today(request))
    )


class DailyCompletionChecklistItem(BaseModel):
    """One assigned checklist item and its state for a selected local date."""

    model_config = ConfigDict(extra="forbid")
    id: int
    label: str
    position: int
    is_completed: bool


class DailyCompletion(BaseModel):
    """The full checklist state for one assignment and local calendar date."""

    model_config = ConfigDict(extra="forbid")
    assignment_id: int
    completion_date: date
    checklist_items: list[DailyCompletionChecklistItem]
    is_complete: bool


class ChecklistCompletionUpdate(BaseModel):
    """Desired state for one checklist item on one local calendar date."""

    model_config = ConfigDict(extra="forbid")
    completion_date: date
    is_completed: bool


class ChecklistCompletionResult(BaseModel):
    """Updated item state and aggregate daily chore status."""

    model_config = ConfigDict(extra="forbid")
    assignment_id: int
    completion_date: date
    checklist_item: DailyCompletionChecklistItem
    is_complete: bool


@router.get(
    "/{family_member_id}/assignments/{assignment_id}/completion",
    response_model=DailyCompletion,
    responses={
        404: {"description": "Family member, assignment, or checklist not found."},
        409: {"description": "The selected family member is inactive."},
        422: {"description": "The date is outside the assignment week."},
    },
    summary="Get a child's checklist completion for a local date",
)
def get_assignment_completion(
    family_member_id: int, assignment_id: int, completion_date: date, request: Request
) -> dict[str, Any]:
    return _invoke(
        lambda: _service(request).get_assignment_completion(
            family_member_id, assignment_id, completion_date
        )
    )


@router.put(
    "/{family_member_id}/assignments/{assignment_id}/checklist-items/"
    "{checklist_item_id}/completion",
    response_model=ChecklistCompletionResult,
    responses={
        404: {"description": "Family member, assignment, or checklist item not found."},
        409: {"description": "The selected family member is inactive."},
        422: {"description": "The date is outside the assignment week."},
    },
    summary="Set a checklist item's completion state for a local date",
)
def update_assignment_checklist_completion(
    family_member_id: int,
    assignment_id: int,
    checklist_item_id: int,
    request: ChecklistCompletionUpdate,
    http_request: Request,
) -> dict[str, Any]:
    return _invoke(
        lambda: _service(http_request).update_assignment_checklist_completion(
            family_member_id,
            assignment_id,
            checklist_item_id,
            request.completion_date,
            request.is_completed,
        )
    )


class CompletionHistoryRecord(BaseModel):
    """One historical local calendar day for an immutable weekly assignment."""

    model_config = ConfigDict(extra="forbid")
    assignment_id: int
    week_start: date
    week_end: date
    chore_name: str
    chore_description: str
    completion_date: date
    completion_status: Literal["complete", "incomplete", "not_yet_recorded"]


class CompletionHistoryPage(BaseModel):
    """A bounded page of historical daily completion records."""

    model_config = ConfigDict(extra="forbid")
    items: list[CompletionHistoryRecord]
    total: int
    limit: int
    offset: int


@router.get(
    "/{family_member_id}/completion-history",
    response_model=CompletionHistoryPage,
    responses={404: {"description": "Family member was not found."}},
    summary="Get a child's historical daily chore completion",
)
def get_family_member_completion_history(
    family_member_id: int,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _invoke(
        lambda: _service(request).get_completion_history(
            family_member_id, limit, offset
        )
    )
