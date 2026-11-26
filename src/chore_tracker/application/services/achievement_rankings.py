"""Family-wide achievement ranking derived from total XP.

Ranking is derived per request from persisted completion facts. It is never
stored and it never changes the configured display order of children.

Each member's XP is calculated by the Quest mapping in
`chore_tracker.application.services.quest_rewards`; callers pass the computed
`lifetime_xp` so this module stays a pure ordering step.
"""

from __future__ import annotations

from typing import Any


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
                "total_xp": member["lifetime_xp"],
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
