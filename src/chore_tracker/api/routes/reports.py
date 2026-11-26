"""Administrator-only weekly report history and reward endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from chore_tracker.api.routes.auth import require_admin, require_same_origin
from chore_tracker.application.services.weekly_reports import (
    DEFAULT_REPORT_ENTRY_PAGE_SIZE,
    MAX_REPORT_ENTRY_PAGE_SIZE,
    WeeklyReportEntry,
    WeeklyReportHeader,
    WeeklyReportReward,
    WeeklyReportService,
    WeeklyReportSummary,
)

router = APIRouter(prefix="/reports", tags=["weekly reports"])
Admin = Annotated[dict[str, Any], Depends(require_admin)]
SameOrigin = Annotated[None, Depends(require_same_origin)]


def _service(request: Request) -> WeeklyReportService:
    return request.app.state.report_service_factory()


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _summary(summary: WeeklyReportSummary) -> dict[str, int]:
    return {
        "family_member_count": summary.family_member_count,
        "total_days": summary.total_days,
        "completed_days": summary.completed_days,
        "incomplete_days": summary.incomplete_days,
    }


def _header(header: WeeklyReportHeader) -> dict[str, Any]:
    return {
        "id": header.id,
        "week_start": header.week_start.isoformat(),
        "week_end": header.week_end.isoformat(),
        "generated_at": _timestamp(header.generated_at),
        "summary": _summary(header.summary),
    }


def _reward(reward: WeeklyReportReward) -> dict[str, Any]:
    return {
        "rewarded_at": _timestamp(reward.rewarded_at),
        "rewarded_by": {
            "administrator_id": reward.administrator_id,
            "email": reward.administrator_email,
        },
    }


def _entry(entry: WeeklyReportEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "family_member_name": entry.family_member_name,
        "chore_name": entry.chore_name,
        "chore_description": entry.chore_description,
        "completed_days": entry.completed_days,
        "incomplete_days": entry.incomplete_days,
        "days": [
            {"date": day.report_date.isoformat(), "status": day.status.value}
            for day in entry.days
        ],
        "reward": None if entry.reward is None else _reward(entry.reward),
    }


@router.get("")
def list_reports(request: Request, administrator: Admin) -> list[dict[str, Any]]:
    """List finalized report headers newest first for administrators."""
    return [_header(header) for header in _service(request).list_reports()]


@router.get("/{week_start}")
def get_report(
    week_start: date,
    request: Request,
    administrator: Admin,
    limit: Annotated[
        int, Query(ge=1, le=MAX_REPORT_ENTRY_PAGE_SIZE)
    ] = DEFAULT_REPORT_ENTRY_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Return one persisted report header and a page of its entries."""
    service = _service(request)
    header = service.get_report_header(week_start)
    if header is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weekly report was not found",
        )
    page = service.get_report_entries(week_start, limit=limit, offset=offset)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weekly report was not found",
        )
    return {
        **_header(header),
        "entries": [_entry(entry) for entry in page.entries],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.put("/{week_start}/entries/{entry_id}/reward")
def mark_report_entry_rewarded(
    week_start: date,
    entry_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    request: Request,
    administrator: Admin,
    origin: SameOrigin,
) -> dict[str, Any]:
    """Record that one child's weekly report reward has been given."""
    reward = _service(request).mark_entry_rewarded(
        week_start, entry_id, administrator["id"]
    )
    if reward is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weekly report entry was not found",
        )
    return _reward(reward)
