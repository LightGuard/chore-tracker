"""Application use case for immutable weekly assignment generation."""

from __future__ import annotations

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
    chore_id: int
    week_start: date
    week_end: date
    chore_name: str
    chore_description: str
    checklist_items: tuple[AssignmentChecklistSnapshot, ...]


class WeeklyAssignmentPersistence(Protocol):
    """Persistence port for atomic weekly assignment generation."""

    def generate(
        self, week_start: date, week_end: date, generated_on: date
    ) -> tuple[WeeklyAssignment, ...]: ...


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


class WeeklyAssignmentGenerationService:
    """Normalize generation inputs and delegate atomic persistence."""

    def __init__(
        self, persistence: WeeklyAssignmentPersistence, timezone_name: str
    ) -> None:
        self._persistence = persistence
        self._timezone = ZoneInfo(timezone_name)

    def generate(
        self, week: date | datetime, *, generated_on: date | None = None
    ) -> tuple[WeeklyAssignment, ...]:
        if generated_on is not None and isinstance(generated_on, datetime):
            raise TypeError("generated_on must be a date, not a datetime")
        normalized = _week_start(week, self._timezone)
        local_generation_date = generated_on or datetime.now(self._timezone).date()
        return self._persistence.generate(
            normalized, normalized + timedelta(days=6), local_generation_date
        )


def generate_weekly_assignments(
    week: date | datetime,
    *,
    persistence: WeeklyAssignmentPersistence,
    timezone_name: str,
    generated_on: date | None = None,
) -> tuple[WeeklyAssignment, ...]:
    """Compatibility-friendly functional entry point with explicit dependencies."""
    return WeeklyAssignmentGenerationService(persistence, timezone_name).generate(
        week, generated_on=generated_on
    )
