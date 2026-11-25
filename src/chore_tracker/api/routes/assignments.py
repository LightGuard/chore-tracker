"""Administrator-only manual weekly assignment generation."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from chore_tracker.api.routes.auth import require_admin, require_same_origin
from chore_tracker.application.services.weekly_assignment_generation import (
    RotationAnchorRequiredError,
    WeeklyAssignment,
    WeeklyAssignmentGenerationResult,
    WeeklyAssignmentGenerationService,
)
from chore_tracker.application.services.weekly_rotation import (
    InsufficientActiveChoresError,
    WeekBeforeRotationAnchorError,
)

router = APIRouter(prefix="/assignments", tags=["weekly assignments"])
Admin = Annotated[dict[str, Any], Depends(require_admin)]
SameOrigin = Annotated[None, Depends(require_same_origin)]


class AssignmentGenerationRequest(BaseModel):
    """A local calendar date in the week to generate."""

    model_config = ConfigDict(extra="forbid")
    week: date


class AssignmentSummary(BaseModel):
    """One assignment returned after generation."""

    id: int
    family_member_id: int
    family_member_name: str
    chore_id: int
    chore_name: str
    week_start: date
    week_end: date


class AssignmentGenerationResponse(BaseModel):
    """Resolved week and whether generation created or reused assignments."""

    week_start: date
    week_end: date
    status: Literal["generated", "already_exists"]
    assignment_count: int
    assignments: list[AssignmentSummary]


def _service(request: Request) -> WeeklyAssignmentGenerationService:
    return request.app.state.assignment_generation_service_factory()


def _summary(assignment: WeeklyAssignment) -> AssignmentSummary:
    return AssignmentSummary(
        id=assignment.id,
        family_member_id=assignment.family_member_id,
        family_member_name=assignment.family_member_name,
        chore_id=assignment.chore_id,
        chore_name=assignment.chore_name,
        week_start=assignment.week_start,
        week_end=assignment.week_end,
    )


def _response(
    result: WeeklyAssignmentGenerationResult,
) -> AssignmentGenerationResponse:
    return AssignmentGenerationResponse(
        week_start=result.week_start,
        week_end=result.week_end,
        status="generated" if result.created else "already_exists",
        assignment_count=len(result.assignments),
        assignments=[_summary(assignment) for assignment in result.assignments],
    )


@router.post("")
def generate_assignments(
    body: AssignmentGenerationRequest,
    request: Request,
    response: Response,
    administrator: Admin,
    origin: SameOrigin,
) -> AssignmentGenerationResponse:
    """Generate one Monday-Sunday week or return its existing assignments.

    Manual generation uses the same planning and persistence path as the
    scheduled rollover. Repeating the request for a generated week returns the
    existing assignments without changing them.
    """
    try:
        result = _service(request).generate_selected_week(body.week)
    except RotationAnchorRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except WeekBeforeRotationAnchorError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except InsufficientActiveChoresError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    if result.created:
        response.status_code = status.HTTP_201_CREATED
    return _response(result)
