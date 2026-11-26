# Weekly assignment rotation policy

## Week initialization

The first assignment week is the first Monday on or after the date the initial
assignment is generated. That Monday is the rotation anchor. The anchor must be
retained as rotation state and supplied when planning later weeks; it must not
be recalculated for every week. The scheduled rollover generates week `W` with
`W` as its initialization date. Manual generation has the additional rules
described in [Manual generation](#manual-generation).

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

## Manual generation

An authenticated administrator can generate a selected week from
**Weekly assignments** on `/admin` or `POST /assignments`. Manual generation
calls the same planning function and atomic persistence as the scheduled
rollover, so the same catalog state, week start, and rotation anchor produce the
same assignments.

The selected local date is normalized to its Monday in the reporting timezone.
The operation is idempotent: requesting an already-generated week returns its
existing assignments with an `already_exists` result and never replaces rows or
snapshots.

On a database with no rotation anchor yet:

- the current week or an earlier week can be generated and becomes the anchor;
- a future week is rejected until the anchor exists, so a manual request cannot
  prevent the scheduled rollover from generating the current week.

After the anchor exists, any week at or after it, including past and future
weeks, can be generated. A week before the anchor is rejected.

Manual generation does not create a weekly report and does not advance the
durable rollover checkpoint. When the scheduled rollover later reaches that
assignment week, it reuses the existing assignments and generates the report for
the preceding week.

## Catalog changes

Family-member and chore activation changes affect the next generated weekly
plan. Chore weight edits behave the same way: the weight captured at generation
stays with that week, and a new weight applies to the next generated week. They
do not cause an already-started week's assignments to be regenerated. Weekly
assignment rows and their checklist snapshots are historical records: the
assignment row keeps the chore weight captured at generation, and each item
keeps its required/optional flag. The database's immutable-history constraints
protect existing assignments.

The next week's plan uses the then-current active members and chores, ordered by
the rules above, and the same original rotation anchor. Existing assignments
must be retained rather than replaced when a week is already generated.

## One-day claims

A child can claim an active chore that the rotation did not assign for the
current Monday-Sunday week, for the current local date only. A claim creates an
immutable one-day record outside `weekly_assignments`; it never adds, replaces,
or regenerates a weekly assignment and never moves the rotation anchor.
Availability is evaluated per local date, so a claimed chore is no longer
available for that date but can be claimed again on a later date while it
remains unassigned for the week. A chore already named by a weekly assignment
for the week is not claimable through this path.

## Implementation boundary

The plan_weekly_assignments function is a pure planning function. It does not
read the system clock, access SQLite, create assignment records, or mutate
existing assignments. The caller supplies the week being planned and the
retained rotation anchor. Persistence and weekly rollover orchestration are
separate responsibilities.
