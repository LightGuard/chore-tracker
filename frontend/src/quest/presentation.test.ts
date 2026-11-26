import { describe, expect, it } from "vitest";
import type {
  DerivedStats,
  DerivedStatsStanding,
  DerivedStatsXpRanking,
} from "../family/api";
import {
  levelForXp,
  questLeaderboard,
  questLevelProgress,
  xpForObjectives,
} from "./presentation";

function standing(
  id: number,
  name: string,
  completed: number,
  streak: number,
  xp = completed * 10,
): DerivedStatsStanding {
  return {
    family_member_id: id,
    display_name: name,
    completed_checklist_items: completed,
    xp,
    complete_days: 0,
    current_streak: streak,
  };
}

function ranking(
  id: number,
  name: string,
  totalXp: number,
  rank: number,
): DerivedStatsXpRanking {
  return {
    family_member_id: id,
    display_name: name,
    total_xp: totalXp,
    rank,
  };
}

function stats(overrides: Partial<DerivedStats> = {}): DerivedStats {
  return {
    family_member_id: 1,
    display_name: "Alex",
    as_of: "2026-11-25",
    timezone: "America/Denver",
    lifetime: {
      completed_checklist_items: 0,
      xp: 0,
      complete_days: 0,
      current_streak: 0,
    },
    current_week: {
      week_start: "2026-11-23",
      week_end: "2026-11-29",
      completed_checklist_items: 0,
      xp: 0,
      complete_days: 0,
      days: [],
    },
    household: {
      active_players: 1,
      weekly_standings: [standing(1, "Alex", 0, 0)],
      xp_rankings: [ranking(1, "Alex", 0, 1)],
    },
    ...overrides,
  };
}

describe("Quest presentation", () => {
  it("maps completed objectives to XP at ten points per weight point", () => {
    expect(xpForObjectives(0, 1)).toBe(0);
    expect(xpForObjectives(1, 1)).toBe(10);
    expect(xpForObjectives(3, 2)).toBe(60);
    expect(xpForObjectives(3, 10)).toBe(300);
    expect(xpForObjectives(-4, 1)).toBe(0);
    expect(xpForObjectives(3, -1)).toBe(0);
  });

  it("awards different XP for the same objectives at different weights", () => {
    expect(xpForObjectives(3, 1)).toBe(30);
    expect(xpForObjectives(3, 3)).toBe(90);
    expect(xpForObjectives(3, 0)).toBe(0);
  });

  it("uses the API-provided weighted XP and ignores the item count", () => {
    const progress = questLevelProgress(
      stats({
        lifetime: {
          completed_checklist_items: 5,
          xp: 1240,
          complete_days: 31,
          current_streak: 4,
        },
        current_week: {
          week_start: "2026-11-23",
          week_end: "2026-11-29",
          completed_checklist_items: 2,
          xp: 380,
          complete_days: 3,
          days: [],
        },
      }),
    );

    expect(progress).toEqual({
      xp: 1240,
      level: 3,
      xpIntoLevel: 240,
      xpForNextLevel: 500,
      progress: 0.48,
      weeklyXp: 380,
    });
  });

  it("calculates level boundaries at 0, 499, and 500 XP", () => {
    expect(levelForXp(0)).toBe(1);
    expect(levelForXp(499)).toBe(1);
    expect(levelForXp(500)).toBe(2);
    expect(levelForXp(1499)).toBe(3);
  });

  it("resets level progress at the 500 XP boundary", () => {
    const boundary = questLevelProgress(
      stats({
        lifetime: {
          completed_checklist_items: 50,
          xp: 500,
          complete_days: 10,
          current_streak: 1,
        },
      }),
    );
    const below = questLevelProgress(
      stats({
        lifetime: {
          completed_checklist_items: 49,
          xp: 490,
          complete_days: 9,
          current_streak: 1,
        },
      }),
    );

    expect(boundary).toMatchObject({
      xp: 500,
      level: 2,
      xpIntoLevel: 0,
      xpForNextLevel: 500,
      progress: 0,
    });
    expect(below).toMatchObject({ xp: 490, level: 1, xpIntoLevel: 490 });
  });

  it("derives achievement rank, player count, and XP gap from total XP", () => {
    const positions = questLeaderboard(
      stats({
        family_member_id: 2,
        household: {
          active_players: 4,
          weekly_standings: [
            standing(3, "Riley", 42, 5, 420),
            standing(2, "Alex", 38, 3, 380),
            standing(4, "Avery", 32, 2, 320),
            standing(1, "Sam", 24, 1, 240),
          ],
          xp_rankings: [
            ranking(3, "Riley", 1240, 1),
            ranking(2, "Alex", 980, 2),
            ranking(4, "Avery", 720, 3),
            ranking(1, "Sam", 610, 4),
          ],
        },
      }),
    );

    expect(positions).toEqual({
      rank: 2,
      playerCount: 4,
      gapToFirstXp: 260,
    });
  });

  it("ignores weekly standings order when deriving achievement rank", () => {
    const positions = questLeaderboard(
      stats({
        family_member_id: 2,
        household: {
          active_players: 4,
          weekly_standings: [
            standing(2, "Alex", 42, 5, 420),
            standing(3, "Riley", 38, 3, 380),
            standing(4, "Avery", 32, 2, 320),
            standing(1, "Sam", 24, 1, 240),
          ],
          xp_rankings: [
            ranking(3, "Riley", 1240, 1),
            ranking(4, "Avery", 980, 2),
            ranking(2, "Alex", 720, 3),
            ranking(1, "Sam", 610, 4),
          ],
        },
      }),
    );

    expect(positions.rank).toBe(3);
    expect(positions.gapToFirstXp).toBe(520);
  });

  it("shares a rank for children tied on total XP", () => {
    const positions = questLeaderboard(
      stats({
        family_member_id: 2,
        household: {
          active_players: 4,
          weekly_standings: [
            standing(3, "Riley", 42, 5, 420),
            standing(2, "Alex", 38, 3, 380),
            standing(4, "Avery", 32, 2, 320),
            standing(1, "Sam", 24, 1, 240),
          ],
          xp_rankings: [
            ranking(3, "Riley", 1240, 1),
            ranking(2, "Alex", 1240, 1),
            ranking(4, "Avery", 720, 3),
            ranking(1, "Sam", 610, 4),
          ],
        },
      }),
    );

    expect(positions.rank).toBe(1);
    expect(positions.gapToFirstXp).toBe(0);
  });

  it("updates the achievement rank when total XP changes", () => {
    const before = questLeaderboard(
      stats({
        family_member_id: 2,
        household: {
          active_players: 2,
          weekly_standings: [standing(2, "Alex", 38, 3, 380)],
          xp_rankings: [
            ranking(3, "Riley", 1240, 1),
            ranking(2, "Alex", 980, 2),
          ],
        },
      }),
    );
    const after = questLeaderboard(
      stats({
        family_member_id: 2,
        household: {
          active_players: 2,
          weekly_standings: [standing(2, "Alex", 38, 3, 380)],
          xp_rankings: [
            ranking(2, "Alex", 1300, 1),
            ranking(3, "Riley", 1240, 2),
          ],
        },
      }),
    );

    expect(before.rank).toBe(2);
    expect(after.rank).toBe(1);
    expect(after.gapToFirstXp).toBe(0);
  });

  it("derives the same rank regardless of the ranking list order", () => {
    const positions = questLeaderboard(
      stats({
        family_member_id: 4,
        household: {
          active_players: 2,
          weekly_standings: [
            standing(4, "Avery", 12, 2, 120),
            standing(3, "Riley", 30, 4, 300),
          ],
          xp_rankings: [
            ranking(4, "Avery", 120, 2),
            ranking(3, "Riley", 300, 1),
          ],
        },
      }),
    );
    const reversed = questLeaderboard(
      stats({
        family_member_id: 4,
        household: {
          active_players: 2,
          weekly_standings: [
            standing(3, "Riley", 30, 4, 300),
            standing(4, "Avery", 12, 2, 120),
          ],
          xp_rankings: [
            ranking(3, "Riley", 300, 1),
            ranking(4, "Avery", 120, 2),
          ],
        },
      }),
    );

    expect(positions).toEqual(reversed);
    expect(positions).toEqual({ rank: 2, playerCount: 2, gapToFirstXp: 180 });
  });

  it("never reports a negative gap when the selected child leads", () => {
    const leader = questLeaderboard(
      stats({
        family_member_id: 1,
        household: {
          active_players: 2,
          weekly_standings: [
            standing(1, "Alex", 22, 4, 220),
            standing(2, "Sam", 10, 1, 100),
          ],
          xp_rankings: [ranking(1, "Alex", 220, 1), ranking(2, "Sam", 100, 2)],
        },
      }),
    );
    expect(leader.rank).toBe(1);
    expect(leader.gapToFirstXp).toBe(0);
  });

  it("returns a null achievement rank when the selected child is not ranked", () => {
    const missing = questLeaderboard(
      stats({
        family_member_id: 99,
        household: {
          active_players: 2,
          weekly_standings: [
            standing(1, "Alex", 22, 4, 220),
            standing(2, "Sam", 10, 1, 100),
          ],
          xp_rankings: [ranking(1, "Alex", 220, 1), ranking(2, "Sam", 100, 2)],
        },
      }),
    );
    expect(missing.rank).toBeNull();
    expect(missing.gapToFirstXp).toBe(0);
  });
});
