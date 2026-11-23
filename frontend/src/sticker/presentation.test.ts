import { describe, expect, it } from "vitest";
import type { CurrentAssignment, DerivedStats, DerivedStatsDay } from "../family/api";
import { stickerWeek } from "./presentation";

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
    today: "2026-11-25",
    checklist_items: [
      { id: 11, label: "Wipe counters", position: 0, is_completed: false },
      { id: 12, label: "Sweep floor", position: 1, is_completed: false },
      { id: 13, label: "Take out trash", position: 2, is_completed: false },
    ],
    is_complete: false,
    ...overrides,
  };
}

describe("Sticker Club v2 presentation", () => {
  it("maps complete days from the derived week to the sticker count and rail", () => {
    const week = stickerWeek(
      stats([
        day(0, "complete"),
        day(1, "complete"),
        day(2, "incomplete", 1),
        day(3, "not_recorded"),
        day(4, "not_recorded"),
        day(5, "not_recorded"),
        day(6, "not_recorded"),
      ]),
    );

    expect(week.count).toBe(2);
    expect(week.days).toHaveLength(7);
    expect(week.days.map((entry) => entry.statusLabel)).toEqual([
      "DONE",
      "DONE",
      "PART",
      "—",
      "—",
      "—",
      "—",
    ]);
    expect(week.days[2].ariaLabel).toBe("Wednesday, incomplete");
  });

  it("adds or removes today's sticker immediately after a checklist change", () => {
    const base = stats([
      day(0, "complete"),
      day(1, "complete"),
      day(2, "not_recorded"),
      day(3, "not_recorded"),
      day(4, "not_recorded"),
      day(5, "not_recorded"),
      day(6, "not_recorded"),
    ]);

    const completedToday = stickerWeek(
      base,
      assignment({
        checklist_items: [
          { id: 11, label: "Wipe counters", position: 0, is_completed: true },
          { id: 12, label: "Sweep floor", position: 1, is_completed: true },
          { id: 13, label: "Take out trash", position: 2, is_completed: true },
        ],
        is_complete: true,
      }),
    );
    expect(completedToday.count).toBe(3);
    expect(completedToday.days[2]).toMatchObject({
      state: "complete",
      isToday: true,
      statusLabel: "DONE",
    });

    const partialToday = stickerWeek(
      base,
      assignment({
        checklist_items: [
          { id: 11, label: "Wipe counters", position: 0, is_completed: true },
          { id: 12, label: "Sweep floor", position: 1, is_completed: false },
          { id: 13, label: "Take out trash", position: 2, is_completed: false },
        ],
        is_complete: false,
      }),
    );
    expect(partialToday.count).toBe(2);
    expect(partialToday.days[2].state).toBe("incomplete");
    expect(partialToday.days[2].isToday).toBe(true);
  });

  it("never fabricates zero when stats are unavailable", () => {
    const week = stickerWeek(null, assignment());

    expect(week.count).toBeNull();
    expect(week.days).toHaveLength(7);
    expect(week.days.every((entry) => entry.state === "unknown")).toBe(true);
    expect(week.days[2]).toMatchObject({
      isToday: true,
      statusLabel: "?",
      ariaLabel: "Wednesday, unavailable, today",
    });
  });

  it("supports zero, all seven, and a fully complete today", () => {
    const zero = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "not_recorded"))),
    );
    expect(zero.count).toBe(0);

    const seven = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "complete"))),
    );
    expect(seven.count).toBe(7);

    const allToday = stickerWeek(
      stats(Array.from({ length: 7 }, (_, index) => day(index, "not_recorded"))),
      assignment({
        checklist_items: [
          { id: 11, label: "Wipe counters", position: 0, is_completed: true },
          { id: 12, label: "Sweep floor", position: 1, is_completed: true },
          { id: 13, label: "Take out trash", position: 2, is_completed: true },
        ],
        is_complete: true,
      }),
    );
    expect(allToday.count).toBe(1);
    expect(allToday.days[2].state).toBe("complete");
  });
});
