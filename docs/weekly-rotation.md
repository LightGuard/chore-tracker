# Weekly assignment rotation policy

## Week initialization

The first assignment week is the first Monday on or after the date the initial
assignment is generated. That Monday is the rotation anchor. The anchor must be
retained as rotation state and supplied when planning later weeks; it must not
be recalculated for every week.

A week is identified by its Monday week_start. Assignment generation is
deterministic for the same active family members, active chores, week start,
and rotation anchor.

## Stable ordering

Only active family members and active chores participate. Family members are
ordered by display_name using case-insensitive comparison, then by ascending
database ID. Chores are ordered by name using case-insensitive comparison,
then by ascending database ID. IDs break ties, including names that differ only
by case.

## Assignment algorithm

Let N be the number of active family members, M the number of active chores,
W the number of whole weeks since the rotation anchor, and i a family member's
zero-based position in stable member order.

When N is greater than zero, generation requires M >= N. The assigned chore
position for member i is:

    (W + i) modulo M

This gives every active child exactly one chore and never assigns the same chore
to two children in the same week. When there are more chores than children,
remaining chores are unassigned for that week. The starting position advances
by one chore each week, so the unassigned chores enter the rotation over time.
When counts are equal, every child advances to the next chore each week.

If there are no active family members, the plan is empty. If there are fewer
active chores than active family members, planning raises
InsufficientActiveChoresError. It does not return a partial plan or silently
reuse chores.

## Catalog changes

Family-member and chore activation changes affect the next generated weekly
plan. They do not cause an already-started week's assignments to be regenerated.
Weekly assignment rows and their checklist snapshots are historical records;
the database's immutable-history constraints protect existing assignments.

The next week's plan uses the then-current active members and chores, ordered by
the rules above, and the same original rotation anchor. Existing assignments
must be retained rather than replaced when a week is already generated.

## Implementation boundary

The plan_weekly_assignments function is a pure planning function. It does not
read the system clock, access SQLite, create assignment records, or mutate
existing assignments. The caller supplies the week being planned and the
retained rotation anchor. Persistence and weekly rollover orchestration are
separate responsibilities.
