"""Unit tests for deterministic weekly chore rotation planning."""

from __future__ import annotations

from chore_tracker.application.services.weekly_rotation import (
    InsufficientActiveChoresError,
    RotationChore,
    RotationFamilyMember,
    first_assignment_week,
    plan_weekly_assignments,
)


def date(year, month, day):
    return __import__("datetime").date(year, month, day)


FIRST_WEEK = date(2026, 11, 16)


def assert_raises(exception_type, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except exception_type as error:
        return error
    raise AssertionError(f"Expected {exception_type.__name__} to be raised")


def members(count: int) -> list[RotationFamilyMember]:
    return [
        RotationFamilyMember(id=index, display_name=f"Child {index}")
        for index in range(1, count + 1)
    ]


def chores(count: int) -> list[RotationChore]:
    return [
        RotationChore(id=index, name=f"Chore {index}") for index in range(1, count + 1)
    ]


def assignments_for(week, child_count: int, chore_count: int):
    return plan_weekly_assignments(
        members(child_count), chores(chore_count), week, FIRST_WEEK
    )


def test_first_assignment_week_is_first_monday_on_or_after_today():
    assert first_assignment_week(date(2026, 11, 11)) == FIRST_WEEK
    assert first_assignment_week(FIRST_WEEK) == FIRST_WEEK


def test_equal_counts_assign_one_distinct_chore_to_each_child():
    result = assignments_for(FIRST_WEEK, child_count=3, chore_count=3)

    assert [(item.family_member_id, item.chore_id) for item in result] == [
        (1, 1),
        (2, 2),
        (3, 3),
    ]


def test_extra_chores_are_left_unassigned_and_rotation_advances_each_week():
    first = assignments_for(FIRST_WEEK, child_count=3, chore_count=5)
    second = assignments_for(date(2026, 11, 23), child_count=3, chore_count=5)

    assert [item.chore_id for item in first] == [1, 2, 3]
    assert [item.chore_id for item in second] == [2, 3, 4]
    assert len({item.chore_id for item in second}) == 3


def test_fewer_chores_than_children_rejects_the_entire_plan():
    error = assert_raises(
        InsufficientActiveChoresError,
        assignments_for,
        FIRST_WEEK,
        child_count=4,
        chore_count=3,
    )

    assert error.family_member_count == 4
    assert error.chore_count == 3


def test_inactive_members_and_chores_are_excluded():
    active_members = [
        RotationFamilyMember(2, "Zoe"),
        RotationFamilyMember(1, "Alex"),
        RotationFamilyMember(3, "Inactive", is_active=False),
    ]
    active_chores = [
        RotationChore(2, "Yard"),
        RotationChore(1, "Kitchen"),
        RotationChore(3, "Inactive", is_active=False),
    ]

    result = plan_weekly_assignments(
        active_members, active_chores, FIRST_WEEK, FIRST_WEEK
    )

    assert [(item.family_member_id, item.chore_id) for item in result] == [
        (1, 1),
        (2, 2),
    ]


def test_ordering_is_stable_and_uses_id_to_break_case_insensitive_ties():
    active_members = [
        RotationFamilyMember(9, "alex"),
        RotationFamilyMember(4, "Alex"),
    ]
    active_chores = [
        RotationChore(8, "kitchen"),
        RotationChore(3, "Kitchen"),
    ]

    result = plan_weekly_assignments(
        active_members, active_chores, FIRST_WEEK, FIRST_WEEK
    )

    assert [(item.family_member_id, item.chore_id) for item in result] == [
        (4, 3),
        (9, 8),
    ]


def test_changes_to_active_catalog_apply_to_next_plan_only():
    original_members = members(2)
    original_chores = chores(3)
    original_week = plan_weekly_assignments(
        original_members, original_chores, FIRST_WEEK, FIRST_WEEK
    )

    next_members = [*original_members, RotationFamilyMember(3, "Child 3")]
    next_chores = [*original_chores, RotationChore(4, "Chore 4")]
    next_week = plan_weekly_assignments(
        next_members, next_chores, date(2026, 11, 23), FIRST_WEEK
    )

    assert [(item.family_member_id, item.chore_id) for item in original_week] == [
        (1, 1),
        (2, 2),
    ]
    assert [(item.family_member_id, item.chore_id) for item in next_week] == [
        (1, 2),
        (2, 3),
        (3, 4),
    ]


def test_no_active_members_produces_no_assignments():
    result = plan_weekly_assignments(
        [RotationFamilyMember(1, "Inactive", is_active=False)],
        chores(0),
        FIRST_WEEK,
        FIRST_WEEK,
    )

    assert result == ()


def test_invalid_rotation_weeks_are_rejected():
    invalid_weeks = [
        (date(2026, 11, 17), FIRST_WEEK),
        (FIRST_WEEK, date(2026, 11, 17)),
        (date(2026, 11, 9), FIRST_WEEK),
    ]
    for week_start, first_week_start in invalid_weeks:
        assert_raises(
            ValueError,
            plan_weekly_assignments,
            members(1),
            chores(1),
            week_start,
            first_week_start,
        )


def test_same_inputs_and_rotation_anchor_produce_identical_assignments():
    first = assignments_for(date(2026, 11, 23), child_count=3, chore_count=5)
    second = assignments_for(date(2026, 11, 23), child_count=3, chore_count=5)

    assert first == second


def test_deactivation_changes_next_week_without_changing_existing_plan():
    active_members = members(3)
    active_chores = chores(3)
    existing_week = plan_weekly_assignments(
        active_members, active_chores, FIRST_WEEK, FIRST_WEEK
    )

    next_week = plan_weekly_assignments(
        [active_members[0], active_members[2]],
        [active_chores[0], active_chores[2]],
        date(2026, 11, 23),
        FIRST_WEEK,
    )

    assert [(item.family_member_id, item.chore_id) for item in existing_week] == [
        (1, 1),
        (2, 2),
        (3, 3),
    ]
    assert [(item.family_member_id, item.chore_id) for item in next_week] == [
        (1, 3),
        (3, 1),
    ]
