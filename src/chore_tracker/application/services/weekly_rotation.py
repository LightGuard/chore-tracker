"""Deterministic weekly chore rotation planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


class InsufficientActiveChoresError(ValueError):
    """Raised when active chores cannot cover every active family member."""

    def __init__(self, family_member_count: int, chore_count: int) -> None:
        self.family_member_count = family_member_count
        self.chore_count = chore_count
        super().__init__(
            "Cannot generate weekly assignments: "
            f"{family_member_count} active family members require at least "
            f"{family_member_count} active chores; found {chore_count}."
        )


@dataclass(frozen=True, slots=True)
class RotationFamilyMember:
    """Family member fields used to establish deterministic ordering."""

    id: int
    display_name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class RotationChore:
    """Chore fields used to establish deterministic ordering."""

    id: int
    name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class WeeklyAssignmentPlan:
    """One planned chore assignment for a family member."""

    family_member_id: int
    chore_id: int


def first_assignment_week(today: date) -> date:
    """Return the first Monday on or after today."""
    return date.fromordinal(today.toordinal() + (7 - today.weekday()) % 7)


def plan_weekly_assignments(
    family_members: Sequence[RotationFamilyMember],
    chores: Sequence[RotationChore],
    week_start: date,
    first_week_start: date,
) -> tuple[WeeklyAssignmentPlan, ...]:
    """Plan one deterministic weekly assignment set.

    Active members and chores are ordered by case-insensitive display name/name,
    then by database ID. Each week advances the starting chore by one position.
    """
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    if first_week_start.weekday() != 0:
        raise ValueError("first_week_start must be a Monday")
    if week_start < first_week_start:
        raise ValueError("week_start cannot precede first_week_start")

    active_members = sorted(
        (member for member in family_members if member.is_active),
        key=lambda member: (member.display_name.casefold(), member.id),
    )
    active_chores = sorted(
        (chore for chore in chores if chore.is_active),
        key=lambda chore: (chore.name.casefold(), chore.id),
    )

    if not active_members:
        return ()
    if len(active_chores) < len(active_members):
        raise InsufficientActiveChoresError(len(active_members), len(active_chores))

    week_index = (week_start - first_week_start).days // 7
    chore_count = len(active_chores)
    return tuple(
        WeeklyAssignmentPlan(
            family_member_id=member.id,
            chore_id=active_chores[(week_index + index) % chore_count].id,
        )
        for index, member in enumerate(active_members)
    )
