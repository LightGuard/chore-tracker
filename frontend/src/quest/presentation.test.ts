import { describe, expect, it } from "vitest";
import type { DerivedStats, DerivedStatsStanding } from "../family/api";
import {
  levelForXp,
  questLeaderboard,
  questLevelProgress,
  xpFromCompletedItems,
} from "./presentation";

function standing(
  id: number,
  name: string,
  completed: number,
  streak: number,
): DerivedStatsStanding {
  return {
    family_member_id: id,
    display_name: name,
    completed_checklist_items: completed,
    complete_days: 0,
    current_streak: streak,
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
      complete_days: 0,
      current_streak: 0,
    },
    current_week: {
      week_start: "2026-11-23",
      week_end: "2026-11-29",
      completed_checklist_items: 0,
      complete_days: 0,
      days: [],
    },
    household: {
      active_players: 1,
      weekly_standings: [standing(1, "Alex", 0, 0)],
    },
    ...overrides,
  };
}

describe("Quest presentation", () => {
  it("maps completed items to XP at ten points each", () => {
    expect(xpFromCompletedItems(0)).toBe(0);
    expect(xpFromCompletedItems(1)).toBe(10);
    expect(xpFromCompletedItems(124)).toBe(1240);
    expect(xpFromCompletedItems(-4)).toBe(0);
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
          complete_days: 10,
          current_streak: 1,
        },
      }),
    );
    const below = questLevelProgress(
      stats({
        lifetime: {
          completed_checklist_items: 49,
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

  it("shows progress within the current level and current-week XP", () => {
    const progress = questLevelProgress(
      stats({
        lifetime: {
          completed_checklist_items: 124,
          complete_days: 31,
          current_streak: 4,
        },
        current_week: {
          week_start: "2026-11-23",
          week_end: "2026-11-29",
          completed_checklist_items: 22,
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
      weeklyXp: 220,
    });
  });

  it("derives rank, player count, and XP gap from weekly standings order", () => {
    const positions = questLeaderboard(
      stats({
        family_member_id: 2,
        household: {
          active_players: 4,
          weekly_standings: [
            standing(3, "Riley", 42, 5),
            standing(2, "Alex", 38, 3),
            standing(4, "Avery", 32, 2),
            standing(1, "Sam", 24, 1),
          ],
        },
      }),
    );

    expect(positions).toEqual({
      rank: 2,
      playerCount: 4,
      gapToFirstXp: 40,
      selected: standing(2, "Alex", 38, 3),
    });
  });

  it("uses the first standing as the leader and never returns a negative gap", () => {
    const leader = questLeaderboard(
      stats({
        household: {
          active_players: 2,
          weekly_standings: [standing(1, "Alex", 22, 4), standing(2, "Sam", 10, 1)],
        },
      }),
    );
    expect(leader.rank).toBe(1);
    expect(leader.gapToFirstXp).toBe(0);

    const missing = questLeaderboard(
      stats({
        family_member_id: 99,
        household: {
          active_players: 2,
          weekly_standings: [standing(1, "Alex", 22, 4), standing(2, "Sam", 10, 1)],
        },
      }),
    );
    expect(missing.rank).toBeNull();
    expect(missing.selected).toBeNull();
    expect(missing.gapToFirstXp).toBe(0);
  });
});
