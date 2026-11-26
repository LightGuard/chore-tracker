"""Family-wide achievement ranking derived from total XP.

Ranking is derived per request from persisted completion facts. It is never
stored and it never changes the configured display order of children.
"""

from __future__ import annotations

from typing import Any

# The application's existing total-XP calculation. Every completed checklist
# item, required or optional, is worth ten XP; see the Quest theme mapping.
XP_PER_COMPLETED_CHECKLIST_ITEM = 10


def total_xp(completed_checklist_items: int) -> int:
    """Return total XP for a count of completed checklist items."""
    return completed_checklist_items * XP_PER_COMPLETED_CHECKLIST_ITEM


def xp_rankings(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank active children by total XP, independent of display order.

    Equal totals share a rank, and the next distinct total skips the occupied
    positions (competition ranking: 1, 1, 3). Ties are listed by case-insensitive
    display name and then id so the response is deterministic; that tie order
    never changes the rank numbers.
    """
    ranked = sorted(
        (
            {
                "family_member_id": member["family_member_id"],
                "display_name": member["display_name"],
                "total_xp": total_xp(member["lifetime_completed_items"]),
            }
            for member in members
            if member["is_active"]
        ),
        key=lambda entry: (
            -entry["total_xp"],
            entry["display_name"].casefold(),
            entry["family_member_id"],
        ),
    )

    rankings: list[dict[str, Any]] = []
    previous_total_xp: int | None = None
    rank = 0
    for position, entry in enumerate(ranked, start=1):
        if entry["total_xp"] != previous_total_xp:
            rank = position
            previous_total_xp = entry["total_xp"]
        rankings.append({**entry, "rank": rank})
    return rankings
