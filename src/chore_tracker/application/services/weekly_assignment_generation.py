"""Application use case for immutable weekly assignment generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class AssignmentChecklistSnapshot:
    """An ordered checklist item captured when a weekly assignment is created."""

    id: int
    source_checklist_item_id: int | None
    label: str
    position: int


@dataclass(frozen=True, slots=True)
class WeeklyAssignment:
    """Persisted weekly assignment and its immutable chore/checklist snapshots."""

    id: int
    family_member_id: int
    family_member_name: str
    chore_id: int
    week_start: date
    week_end: date
    chore_name: str
    chore_description: str
    checklist_items: tuple[AssignmentChecklistSnapshot, ...]


@dataclass(frozen=True, slots=True)
class WeeklyAssignmentGenerationResult:
    """Outcome of one assignment-generation request."""

    week_start: date
    week_end: date
    created: bool
    assignments: tuple[WeeklyAssignment, ...]


class RotationAnchorRequiredError(ValueError):
    """Raised when a future week is requested before a rotation anchor exists."""

    def __init__(self, week_start: date, current_week_start: date) -> None:
        self.week_start = week_start
        self.current_week_start = current_week_start
        super().__init__(
            "Cannot generate weekly assignments for "
            f"{week_start.isoformat()} before the rotation anchor exists. "
            "Generate the current week "
            f"({current_week_start.isoformat()}) or an earlier week first."
        )


class WeeklyAssignmentPersistence(Protocol):
    """Persistence port for atomic weekly assignment generation."""

    def rotation_anchor(self) -> date | None:
        """Return the immutable rotation anchor, or None before any generation."""
        ...

    def generate(
        self, week_start: date, week_end: date, generated_on: date
    ) -> WeeklyAssignmentGenerationResult:
        """Atomically generate or return one week's assignments."""
        ...


def _week_start(value: date | datetime, timezone: ZoneInfo) -> date:
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


def _normalized_week(value: date | datetime, timezone: ZoneInfo) -> date:
    """Return a Monday week start that can represent a full Monday-Sunday week."""
    normalized = _week_start(value, timezone)
    if normalized > date.max - timedelta(days=6):
        raise ValueError("week must end on or before 9999-12-31")
    return normalized


class WeeklyAssignmentGenerationService:
    """Normalize generation inputs and delegate atomic persistence."""

    def __init__(
        self,
        persistence: WeeklyAssignmentPersistence,
        timezone_name: str,
        *,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._persistence = persistence
        self._timezone = ZoneInfo(timezone_name)
        self._today = today or (lambda: datetime.now(self._timezone).date())

    def generate(
        self, week: date | datetime, *, generated_on: date | None = None
    ) -> WeeklyAssignmentGenerationResult:
        """Generate one week using the caller-supplied anchor initialization date."""
        if generated_on is not None and isinstance(generated_on, datetime):
            raise TypeError("generated_on must be a date, not a datetime")
        normalized = _normalized_week(week, self._timezone)
        local_generation_date = generated_on or self._today()
        return self._persistence.generate(
            normalized,
            normalized + timedelta(days=6),
            local_generation_date,
        )

    def generate_selected_week(
        self, week: date | datetime
    ) -> WeeklyAssignmentGenerationResult:
        """Generate a week selected in the administrator UI.

        When the rotation anchor does not exist yet, the selected week becomes
        the anchor unless it is in the future. Future weeks require an anchor
        first so a manual request cannot prevent the scheduled rollover from
        generating the current week.
        """
        normalized = _normalized_week(week, self._timezone)
        current_week = _week_start(self._today(), self._timezone)
        if normalized > current_week and self._persistence.rotation_anchor() is None:
            raise RotationAnchorRequiredError(normalized, current_week)
        return self._persistence.generate(
            normalized,
            normalized + timedelta(days=6),
            normalized,
        )


def generate_weekly_assignments(
    week: date | datetime,
    *,
    persistence: WeeklyAssignmentPersistence,
    timezone_name: str,
    generated_on: date | None = None,
) -> tuple[WeeklyAssignment, ...]:
    """Compatibility-friendly functional entry point with explicit dependencies."""
    return (
        WeeklyAssignmentGenerationService(persistence, timezone_name)
        .generate(week, generated_on=generated_on)
        .assignments
    )
