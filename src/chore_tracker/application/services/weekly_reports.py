"""Application use cases for immutable weekly completion reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

DEFAULT_REPORT_ENTRY_PAGE_SIZE = 25
MAX_REPORT_ENTRY_PAGE_SIZE = 100


class WeeklyReportError(Exception):
    """Base class for weekly report use-case failures."""


class WeeklyReportIncompleteError(WeeklyReportError):
    """An existing report row was found before its snapshot was finalized."""


class DailyStatus(StrEnum):
    """Persisted completion status for one report day."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class WeeklyReportDay:
    """One Monday-Sunday report day and its persisted completion status."""

    report_date: date
    status: DailyStatus


@dataclass(frozen=True, slots=True)
class WeeklyReportReward:
    """Persisted audit record for one child's rewarded weekly report."""

    rewarded_at: datetime
    administrator_id: int
    administrator_email: str


@dataclass(frozen=True, slots=True)
class WeeklyReportEntry:
    """Persisted report entry for one child's weekly assignment."""

    id: int
    weekly_assignment_id: int
    family_member_id: int
    family_member_name: str
    chore_name: str
    chore_description: str
    completed_days: int
    incomplete_days: int
    days: tuple[WeeklyReportDay, ...]
    reward: WeeklyReportReward | None


@dataclass(frozen=True, slots=True)
class WeeklyReportSummary:
    """Family-wide totals persisted with a report header."""

    family_member_count: int
    total_days: int
    completed_days: int
    incomplete_days: int


@dataclass(frozen=True, slots=True)
class WeeklyReport:
    """A finalized, immutable weekly report and all of its entries."""

    id: int
    week_start: date
    week_end: date
    generated_at: datetime
    summary: WeeklyReportSummary
    entries: tuple[WeeklyReportEntry, ...]


@dataclass(frozen=True, slots=True)
class WeeklyReportHeader:
    """A finalized report header without its entries."""

    id: int
    week_start: date
    week_end: date
    generated_at: datetime
    summary: WeeklyReportSummary


@dataclass(frozen=True, slots=True)
class WeeklyReportEntryPage:
    """A stable page of report entries ordered for administrator display."""

    report_id: int
    entries: tuple[WeeklyReportEntry, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AssignmentReportSource:
    """Assignment snapshot and per-day completed item counts for a report."""

    weekly_assignment_id: int
    family_member_id: int
    family_member_name: str
    chore_name: str
    chore_description: str
    checklist_item_count: int
    required_checklist_item_count: int
    required_completed_item_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class WeeklyReportEntryDraft:
    """Calculated entry content ready for atomic persistence."""

    weekly_assignment_id: int
    family_member_id: int
    family_member_name: str
    chore_name: str
    chore_description: str
    completed_days: int
    incomplete_days: int
    days: tuple[WeeklyReportDay, ...]


@dataclass(frozen=True, slots=True)
class WeeklyReportDraft:
    """Calculated report header and entries ready for atomic persistence."""

    week_start: date
    week_end: date
    generated_at: datetime
    summary: WeeklyReportSummary
    entries: tuple[WeeklyReportEntryDraft, ...]


class WeeklyReportPersistence(Protocol):
    """Persistence port for atomic report generation and snapshot retrieval."""

    def generate(
        self, week_start: date, week_end: date, generated_at: datetime
    ) -> WeeklyReport: ...

    def list(self) -> tuple[WeeklyReportHeader, ...]: ...

    def get_header(self, week_start: date) -> WeeklyReportHeader | None: ...

    def get(self, week_start: date) -> WeeklyReport | None: ...

    def get_entries(
        self, week_start: date, limit: int, offset: int
    ) -> WeeklyReportEntryPage | None: ...

    def mark_rewarded(
        self,
        week_start: date,
        entry_id: int,
        administrator_id: int,
        rewarded_at: datetime,
    ) -> WeeklyReportReward | None: ...


def _normalize_week(value: date | datetime, timezone: ZoneInfo) -> date:
    """Normalize a date or aware datetime to Monday in the configured timezone."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("week must be a date or timezone-aware datetime")
        local_date = value.astimezone(timezone).date()
    elif isinstance(value, date):
        local_date = value
    else:
        raise TypeError("week must be a date or timezone-aware datetime")
    return local_date - timedelta(days=local_date.weekday())


def _normalize_timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a timezone-aware datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _validate_page(limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= MAX_REPORT_ENTRY_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_REPORT_ENTRY_PAGE_SIZE}")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise TypeError("offset must be an integer")
    if offset < 0:
        raise ValueError("offset must not be negative")


def build_weekly_report_draft(
    week_start: date,
    week_end: date,
    generated_at: datetime,
    assignments: tuple[AssignmentReportSource, ...],
) -> WeeklyReportDraft:
    """Calculate an immutable report snapshot from persisted assignment data.

    A day is complete only when the assignment has at least one checklist
    snapshot item and every snapshot item has a persisted completion record
    marked complete for that day. Missing records are incomplete, not errors.
    """
    if not isinstance(week_start, date) or isinstance(week_start, datetime):
        raise TypeError("week_start must be a date")
    if not isinstance(week_end, date) or isinstance(week_end, datetime):
        raise TypeError("week_end must be a date")
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    if week_end != week_start + timedelta(days=6):
        raise ValueError("week_end must be six days after week_start")
    if not isinstance(assignments, tuple):
        raise TypeError("assignments must be a tuple")

    normalized_generated_at = _normalize_timestamp(generated_at)
    assignment_ids = set()
    entry_drafts = []
    ordered = sorted(
        assignments,
        key=lambda item: (
            item.family_member_name.casefold(),
            item.family_member_id,
            item.weekly_assignment_id,
        ),
    )
    for assignment in ordered:
        if assignment.weekly_assignment_id in assignment_ids:
            raise ValueError("weekly assignment IDs must be unique")
        assignment_ids.add(assignment.weekly_assignment_id)
        if assignment.checklist_item_count < 0:
            raise ValueError("checklist item count must not be negative")
        if (
            assignment.required_checklist_item_count < 0
            or assignment.required_checklist_item_count
            > assignment.checklist_item_count
        ):
            raise ValueError("required checklist item count is invalid")
        if len(assignment.required_completed_item_counts) != 7:
            raise ValueError("completed item counts must cover seven days")
        if any(
            count < 0 or count > assignment.required_checklist_item_count
            for count in assignment.required_completed_item_counts
        ):
            raise ValueError("completed item counts must be within the checklist")
        if not assignment.family_member_name.strip():
            raise ValueError("family member name must not be blank")
        if not assignment.chore_name.strip():
            raise ValueError("chore name must not be blank")

        days = tuple(
            WeeklyReportDay(
                report_date=week_start + timedelta(days=day_index),
                status=(
                    DailyStatus.COMPLETE
                    if assignment.checklist_item_count > 0
                    and completed_count == assignment.required_checklist_item_count
                    else DailyStatus.INCOMPLETE
                ),
            )
            for day_index, completed_count in enumerate(
                assignment.required_completed_item_counts
            )
        )
        completed_days = sum(day.status is DailyStatus.COMPLETE for day in days)
        incomplete_days = len(days) - completed_days
        entry_drafts.append(
            WeeklyReportEntryDraft(
                weekly_assignment_id=assignment.weekly_assignment_id,
                family_member_id=assignment.family_member_id,
                family_member_name=assignment.family_member_name,
                chore_name=assignment.chore_name,
                chore_description=assignment.chore_description,
                completed_days=completed_days,
                incomplete_days=incomplete_days,
                days=days,
            )
        )

    completed_days = sum(entry.completed_days for entry in entry_drafts)
    incomplete_days = sum(entry.incomplete_days for entry in entry_drafts)
    return WeeklyReportDraft(
        week_start=week_start,
        week_end=week_end,
        generated_at=normalized_generated_at,
        summary=WeeklyReportSummary(
            family_member_count=len(entry_drafts),
            total_days=len(entry_drafts) * 7,
            completed_days=completed_days,
            incomplete_days=incomplete_days,
        ),
        entries=tuple(entry_drafts),
    )


class WeeklyReportService:
    """Normalize report requests and delegate atomic snapshot persistence."""

    def __init__(
        self, persistence: WeeklyReportPersistence, timezone_name: str
    ) -> None:
        self._persistence = persistence
        self._timezone = ZoneInfo(timezone_name)

    def generate(
        self, week: date | datetime, *, generated_at: datetime | None = None
    ) -> WeeklyReport:
        normalized = _normalize_week(week, self._timezone)
        timestamp = _normalize_timestamp(
            generated_at if generated_at is not None else datetime.now(UTC)
        )
        return self._persistence.generate(
            normalized, normalized + timedelta(days=6), timestamp
        )

    def get_report(self, week: date | datetime) -> WeeklyReport | None:
        return self._persistence.get(_normalize_week(week, self._timezone))

    def list_reports(self) -> tuple[WeeklyReportHeader, ...]:
        return self._persistence.list()

    def get_report_header(self, week: date | datetime) -> WeeklyReportHeader | None:
        return self._persistence.get_header(_normalize_week(week, self._timezone))

    def get_report_entries(
        self,
        week: date | datetime,
        *,
        limit: int = DEFAULT_REPORT_ENTRY_PAGE_SIZE,
        offset: int = 0,
    ) -> WeeklyReportEntryPage | None:
        _validate_page(limit, offset)
        return self._persistence.get_entries(
            _normalize_week(week, self._timezone), limit, offset
        )

    def mark_entry_rewarded(
        self,
        week: date | datetime,
        entry_id: int,
        administrator_id: int,
        *,
        rewarded_at: datetime | None = None,
    ) -> WeeklyReportReward | None:
        """Record a reward for one child's report entry.

        Returning ``None`` means the report week or entry was not found. A
        repeated request returns the original audit record instead of creating
        a conflicting duplicate; the first marking is the recorded action.
        """
        timestamp = _normalize_timestamp(
            rewarded_at if rewarded_at is not None else datetime.now(UTC)
        )
        return self._persistence.mark_rewarded(
            _normalize_week(week, self._timezone),
            entry_id,
            administrator_id,
            timestamp,
        )


def generate_weekly_report(
    week: date | datetime,
    *,
    persistence: WeeklyReportPersistence,
    timezone_name: str,
    generated_at: datetime | None = None,
) -> WeeklyReport:
    """Compatibility-friendly functional entry point with explicit dependencies."""
    return WeeklyReportService(persistence, timezone_name).generate(
        week, generated_at=generated_at
    )
