"""Quest's mapping from the shared chore weight to experience points.

The shared chore domain stores a reward-neutral weight (0-10) and snapshots it
onto each weekly assignment. Quest reads the snapshot rather than the live
catalog, so editing a chore's weight never rewrites rewards for an assignment
that already exists.

XP per completed checklist item is:

    XP = chore weight x 10

With the documented default weight of 1 this preserves the previous 10 XP per
completed item, so introducing weights did not change existing rewards. A weight
of 0 awards no XP while the completion still counts in every non-reward fact.

Keep this mapping here, separate from the chore domain and any other reward
system, so Quest rewards can change without touching shared chore behavior.
"""

from __future__ import annotations

QUEST_XP_PER_ITEM_WEIGHT = 10


def xp_for_weighted_items(weighted_items: int) -> int:
    """Return Quest XP for the sum of chore weights across completed items."""
    return max(0, weighted_items) * QUEST_XP_PER_ITEM_WEIGHT
