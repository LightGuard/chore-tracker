import { describe, expect, it } from "vitest";
import type { CurrentAssignment, DerivedStats, DerivedStatsDay } from "../family/api";
import { stickerWeek, stickersForWeight } from "./presentation";

function day(
  index: number,
  state: DerivedStatsDay["state"],
  completed = 0,
): DerivedStatsDay {
  const date = new Date(Date.UTC(2026, 10, 23 + index));
  return {
    date: date.toISOString().slice(0, 10),
    completed_checklist_items: completed,
    total_checklist_items: 3,
    state,
  };
}

function stats(days: DerivedStatsDay[]): DerivedStats {
  return {
    family_member_id: 1,
    display_name: "Alex",
    as_of: "2026-11-25",
    timezone: "America/Denver",
    lifetime: {
      completed_checklist_items: 13,
      complete_days: 4,
      current_streak: 2,
    },
    current_week: {
      week_start: "2026-11-23",
      week_end: "2026-11-29",
      completed_checklist_items: 13,
      complete_days: days.filter((entry) => entry.state === "complete").length,
      days,
    },
    household: {
      active_players: 7,
      weekly_standings: [
        {
          family_member_id: 1,
          display_name: "Alex",
          completed_checklist_items: 13,
          complete_days: 4,
          current_streak: 2,
        },
      ],
      xp_rankings: [
        {
          family_member_id: 1,
          display_name: "Alex",
          total_xp: 130,
          rank: 1,
        },
      ],
    },
  };
}

function assignment(overrides: Partial<CurrentAssignment> = {}): CurrentAssignment {
  return {
    id: 10,
    family_member_id: 1,
    week_start: "2026-11-23",
    week_end: "2026-11-29",
    chore_name: "Kitchen",
    chore_description: "Wipe and sweep after dinner.",
    chore_weight: 1,
    today: "2026-11-25",
    checklist_items: [
      { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: false },
      { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: false },
      { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: false },
    ],
    is_complete: false,
    ...overrides,
  };
}

function fullyCompleteToday(
  overrides: Partial<CurrentAssignment> = {},
): CurrentAssignment {
  return assignment({
    checklist_items: [
      { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: true },
      { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: true },
      { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: true },
    ],
    is_complete: true,
    ...overrides,
  });
}

const twoCompleteDays = [
  day(0, "complete"),
  day(1, "complete"),
  day(2, "not_recorded"),
  day(3, "not_recorded"),
  day(4, "not_recorded"),
  day(5, "not_recorded"),
  day(6, "not_recorded"),
];

describe("Sticker Club weight mapping", () => {
  it("mints one sticker per weight point and clamps defensive values", () => {
    expect(stickersForWeight(0)).toBe(0);
    expect(stickersForWeight(1)).toBe(1);
    expect(stickersForWeight(2)).toBe(2);
    expect(stickersForWeight(10)).toBe(10);
    expect(stickersForWeight(-3)).toBe(0);
    expect(stickersForWeight(11)).toBe(10);
    expect(stickersForWeight(2.9)).toBe(2);
    expect(stickersForWeight(Number.NaN)).toBe(0);
  });
});

describe("Sticker Club v2 presentation", () => {
  it("multiplies complete days by the chore weight to count stickers", () => {
    const week = stickerWeek(stats(twoCompleteDays), assignment({ chore_weight: 2 }));

    expect(week.perDay).toBe(2);
    expect(week.completeDays).toBe(2);
    expect(week.count).toBe(4);
    expect(week.days).toHaveLength(7);
    expect(week.days.map((entry) => entry.statusLabel)).toEqual([
      "DONE",
      "DONE",
      "—",
      "—",
      "—",
      "—",
      "—",
    ]);
    expect(week.days[0].earned).toBe(2);
    expect(week.days[0].ariaLabel).toBe("Monday, complete, 2 stickers");
    expect(week.days[2].earned).toBe(0);
  });

  it("keeps the one-sticker-per-day baseline at weight 1", () => {
    const week = stickerWeek(stats(twoCompleteDays), assignment({ chore_weight: 1 }));

    expect(week.count).toBe(2);
    expect(week.days[0].earned).toBe(1);
    expect(week.days[0].ariaLabel).toBe("Monday, complete, 1 sticker");
  });

  it("mints no stickers for a weight-0 chore while the days stay complete", () => {
    const week = stickerWeek(stats(twoCompleteDays), assignment({ chore_weight: 0 }));

    expect(week.count).toBe(0);
    expect(week.completeDays).toBe(2);
    expect(week.days[0].state).toBe("complete");
    expect(week.days[0].earned).toBe(0);
    expect(week.days[0].ariaLabel).toBe("Monday, complete");
  });

  it("adds or removes today's weighted stickers after a checklist change", () => {
    const base = stats(twoCompleteDays);
    const completedToday = stickerWeek(
      base,
      fullyCompleteToday({ chore_weight: 2 }),
    );

    expect(completedToday.count).toBe(6);
    expect(completedToday.days[2]).toMatchObject({
      state: "complete",
      isToday: true,
      statusLabel: "DONE",
      earned: 2,
    });

    const partialToday = stickerWeek(
      base,
      assignment({
        checklist_items: [
          { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: true },
          { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: false },
          { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: false },
        ],
      }),
    );
    expect(partialToday.count).toBe(2);
    expect(partialToday.days[2].state).toBe("incomplete");
    expect(partialToday.days[2].earned).toBe(0);
  });

  it("never fabricates a count when stats are unavailable", () => {
    const week = stickerWeek(null, assignment({ chore_weight: 2 }));

    expect(week.count).toBeNull();
    expect(week.completeDays).toBeNull();
    expect(week.perDay).toBe(2);
    expect(week.days).toHaveLength(7);
    expect(week.days.every((entry) => entry.state === "unknown")).toBe(true);
    expect(week.days[2]).toMatchObject({
      isToday: true,
      statusLabel: "?",
      earned: null,
      ariaLabel: "Wednesday, unavailable, today",
    });
  });

  it("cannot count stickers without an assignment weight", () => {
    const week = stickerWeek(stats(twoCompleteDays));

    expect(week.count).toBeNull();
    expect(week.perDay).toBeNull();
    expect(week.days[0]).toMatchObject({
      state: "complete",
      earned: null,
      ariaLabel: "Monday, complete",
    });
  });

  it("supports zero, all seven, and the maximum weighted week", () => {
    const zero = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "not_recorded"))),
      assignment(),
    );
    expect(zero.count).toBe(0);

    const seven = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "complete"))),
      fullyCompleteToday(),
    );
    expect(seven.count).toBe(7);

    const maxWeight = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "complete"))),
      fullyCompleteToday({ chore_weight: 10 }),
    );
    expect(maxWeight.count).toBe(70);

    const allToday = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "not_recorded"))),
      fullyCompleteToday(),
    );
    expect(allToday.count).toBe(1);
    expect(allToday.days[2].state).toBe("complete");
  });
});
