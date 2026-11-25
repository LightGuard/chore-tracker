"""Unauthenticated child-facing family selection and assignment endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/family-members", tags=["child views"])

# Keep the integration-test seam without a settings route dependency.
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


def _report_timezone(request: Request) -> str:
    settings_provider = globals().get("get_settings")
    if settings_provider is not None:
        return settings_provider().report_timezone
    return request.app.state.settings.report_timezone


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
    theme_id: str | None = None


class ThemeUpdate(BaseModel):
    """A requested theme id."""

    model_config = ConfigDict(extra="forbid")
    theme_id: str


class ThemeUpdateResult(BaseModel):
    """The stored theme id."""

    model_config = ConfigDict(extra="forbid")
    theme_id: str


class AssignmentChecklistItem(BaseModel):
    """One immutable checklist snapshot and its completion state for today."""

    model_config = ConfigDict(extra="forbid")
    id: int
    label: str
    position: int
    is_required: bool
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


@router.put(
    "/{family_member_id}/theme",
    response_model=ThemeUpdateResult,
    responses={
        404: {"description": "Family member was not found."},
        409: {"description": "The family member is inactive."},
        422: {"description": "The theme id is not available."},
    },
    summary="Set a child's theme preference",
)
def update_family_member_theme(
    family_member_id: int,
    body: ThemeUpdate,
    request: Request,
) -> dict[str, str]:
    return _invoke(
        lambda: request.app.state.theme_service.set_family_member_theme(
            family_member_id, body.theme_id
        )
    )


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
        lambda: _service(request).get_current_assignment(
            family_member_id, _today(request)
        )
    )


class DerivedStatsDay(BaseModel):
    """One day in the current Monday-Sunday week."""

    model_config = ConfigDict(extra="forbid")
    date: date
    completed_checklist_items: int
    total_checklist_items: int
    state: Literal["complete", "incomplete", "not_recorded"]


class DerivedStatsLifetime(BaseModel):
    """Lifetime completion facts for one child."""

    model_config = ConfigDict(extra="forbid")
    completed_checklist_items: int
    complete_days: int
    current_streak: int


class DerivedStatsCurrentWeek(BaseModel):
    """Current-week completion facts and per-day states."""

    model_config = ConfigDict(extra="forbid")
    week_start: date
    week_end: date
    completed_checklist_items: int
    complete_days: int
    days: list[DerivedStatsDay]


class DerivedStatsStanding(BaseModel):
    """One active child in the household weekly standings."""

    model_config = ConfigDict(extra="forbid")
    family_member_id: int
    display_name: str
    completed_checklist_items: int
    complete_days: int
    current_streak: int


class DerivedStatsHousehold(BaseModel):
    """Active household counts and generic weekly standings."""

    model_config = ConfigDict(extra="forbid")
    active_players: int
    weekly_standings: list[DerivedStatsStanding]


class DerivedStats(BaseModel):
    """Theme-neutral completion facts shared by family-facing themes."""

    model_config = ConfigDict(extra="forbid")
    family_member_id: int
    display_name: str
    as_of: date
    timezone: str
    lifetime: DerivedStatsLifetime
    current_week: DerivedStatsCurrentWeek
    household: DerivedStatsHousehold


@router.get(
    "/{family_member_id}/derived-stats",
    response_model=DerivedStats,
    responses={
        404: {"description": "Family member was not found."},
        409: {"description": "The selected family member is inactive."},
    },
    summary="Get generic completion facts for a child",
)
def get_family_member_derived_stats(
    family_member_id: int, request: Request
) -> dict[str, Any]:
    return _invoke(
        lambda: _service(request).get_derived_stats(
            family_member_id, _today(request), _report_timezone(request)
        )
    )


class DailyCompletionChecklistItem(BaseModel):
    """One assigned checklist item and its state for a selected local date."""

    model_config = ConfigDict(extra="forbid")
    id: int
    label: str
    position: int
    is_required: bool
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
            family_member_id, limit, offset, _today(request)
        )
    )
