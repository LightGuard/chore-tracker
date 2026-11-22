"""Durable orchestration for the Monday report and assignment rollover."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from chore_tracker.application.services.weekly_assignment_generation import (
    WeeklyAssignmentGenerationService,
)
from chore_tracker.application.services.weekly_reports import WeeklyReportService

logger = logging.getLogger(__name__)


class WeeklyRolloverPersistence(Protocol):
    """Durable checkpoint for the newest completed rollover week."""

    def last_completed_week_start(self) -> date | None: ...

    def mark_completed(self, week_start: date, completed_at: datetime) -> None: ...


@dataclass(frozen=True, slots=True)
class WeeklyRolloverResult:
    """Outcome of one completed report and assignment rollover."""

    assignment_week_start: date
    report_week_start: date
    report_id: int
    assignment_count: int


def _normalize_now(value: datetime | None, timezone: ZoneInfo) -> datetime:
    if value is None:
        return datetime.now(timezone)
    if not isinstance(value, datetime):
        raise TypeError("now must be a timezone-aware datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return value.astimezone(timezone)


def _scheduled_instant(
    week_start: date, delivery_time: time, timezone: ZoneInfo
) -> datetime:
    return datetime.combine(week_start, delivery_time, tzinfo=timezone)


def latest_due_week_start(
    now: datetime, delivery_time: time, timezone: ZoneInfo
) -> date:
    """Return the Monday of the most recent delivery time at or before now."""
    monday = now.date() - timedelta(days=now.weekday())
    if now >= _scheduled_instant(monday, delivery_time, timezone):
        return monday
    return monday - timedelta(days=7)


def next_run_at(now: datetime, delivery_time: time, timezone: ZoneInfo) -> datetime:
    """Return the first configured Monday delivery time strictly after now."""
    monday = now.date() - timedelta(days=now.weekday())
    candidate = _scheduled_instant(monday, delivery_time, timezone)
    if candidate <= now:
        candidate = _scheduled_instant(
            monday + timedelta(days=7), delivery_time, timezone
        )
    return candidate


class WeeklyRolloverService:
    """Generate the previous week's report and the new week's assignments.

    Each step is atomic and idempotent. The durable checkpoint advances only
    after both steps commit, so a crash or failure is retried safely without
    exposing a partial report or duplicating assignments.
    """

    def __init__(
        self,
        *,
        reports: WeeklyReportService,
        assignments: WeeklyAssignmentGenerationService,
        persistence: WeeklyRolloverPersistence,
        timezone_name: str,
        delivery_time: time,
    ) -> None:
        if delivery_time.tzinfo is not None:
            raise ValueError("delivery_time must not include a timezone")
        self._reports = reports
        self._assignments = assignments
        self._persistence = persistence
        self._timezone = ZoneInfo(timezone_name)
        self._delivery_time = delivery_time

    def latest_due_week_start(self, now: datetime | None = None) -> date:
        local_now = _normalize_now(now, self._timezone)
        return latest_due_week_start(local_now, self._delivery_time, self._timezone)

    def next_run_at(self, now: datetime | None = None) -> datetime:
        local_now = _normalize_now(now, self._timezone)
        return next_run_at(local_now, self._delivery_time, self._timezone)

    def due_weeks(self, now: datetime | None = None) -> tuple[date, ...]:
        """Return every unprocessed Monday up to the latest due delivery time.

        On the first run there is no durable checkpoint, so only the most recent
        due Monday is recovered. Later runs replay each missed Monday in order so
        reports and assignments are never skipped after downtime.
        """
        local_now = _normalize_now(now, self._timezone)
        latest = latest_due_week_start(local_now, self._delivery_time, self._timezone)
        last_completed = self._persistence.last_completed_week_start()
        if last_completed is None:
            return (latest,)
        if last_completed.weekday() != 0:
            raise ValueError("last completed rollover week must be a Monday")
        if latest <= last_completed:
            return ()

        weeks = []
        candidate = last_completed + timedelta(days=7)
        while candidate <= latest:
            weeks.append(candidate)
            candidate += timedelta(days=7)
        return tuple(weeks)

    def run_due(self, now: datetime | None = None) -> tuple[WeeklyRolloverResult, ...]:
        """Process every due rollover in week order, stopping at the first failure."""
        local_now = _normalize_now(now, self._timezone)
        return tuple(
            self._run_week(week_start, local_now)
            for week_start in self.due_weeks(local_now)
        )

    def _run_week(
        self, week_start: date, completed_at: datetime
    ) -> WeeklyRolloverResult:
        report_week_start = week_start - timedelta(days=7)
        logger.info(
            "Starting weekly rollover reporting_week=%s assignment_week=%s",
            report_week_start.isoformat(),
            week_start.isoformat(),
        )
        try:
            report = self._reports.generate(
                report_week_start, generated_at=completed_at
            )
            assignments = self._assignments.generate(
                week_start, generated_on=week_start
            )
            self._persistence.mark_completed(week_start, completed_at)
        except Exception as error:
            logger.exception(
                "Weekly rollover failed reporting_week=%s assignment_week=%s "
                "outcome=failed error_type=%s",
                report_week_start.isoformat(),
                week_start.isoformat(),
                type(error).__name__,
            )
            raise

        logger.info(
            "Weekly rollover completed reporting_week=%s assignment_week=%s "
            "outcome=completed report_id=%s assignment_count=%d",
            report_week_start.isoformat(),
            week_start.isoformat(),
            report.id,
            len(assignments),
        )
        return WeeklyRolloverResult(
            assignment_week_start=week_start,
            report_week_start=report_week_start,
            report_id=report.id,
            assignment_count=len(assignments),
        )
