import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CurrentAssignment, DerivedStats, DerivedStatsDay } from "../family/api";
import {
  StickerAssignmentView,
  StickerHeaderCount,
} from "./StickerAssignmentView";
import { stickerWeek } from "./presentation";

afterEach(cleanup);

function day(index: number, state: DerivedStatsDay["state"]): DerivedStatsDay {
  return {
    date: new Date(Date.UTC(2026, 10, 23 + index)).toISOString().slice(0, 10),
    completed_checklist_items: state === "complete" ? 3 : state === "incomplete" ? 1 : 0,
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
      completed_checklist_items: 12,
      complete_days: 3,
      current_streak: 2,
    },
    current_week: {
      week_start: "2026-11-23",
      week_end: "2026-11-29",
      completed_checklist_items: 12,
      complete_days: days.filter((entry) => entry.state === "complete").length,
      days,
    },
    household: {
      active_players: 7,
      weekly_standings: [
        {
          family_member_id: 1,
          display_name: "Alex",
          completed_checklist_items: 12,
          complete_days: 3,
          current_streak: 2,
        },
      ],
      xp_rankings: [
        {
          family_member_id: 1,
          display_name: "Alex",
          total_xp: 120,
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
    today: "2026-11-25",
    checklist_items: [
      { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: true },
      { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: true },
      { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: true },
    ],
    is_complete: true,
    ...overrides,
  };
}

function week(days: DerivedStatsDay[], current = assignment()) {
  return stickerWeek(stats(days), current);
}

const baseDays = [
  day(0, "complete"),
  day(1, "incomplete"),
  day(2, "not_recorded"),
  day(3, "not_recorded"),
  day(4, "not_recorded"),
  day(5, "not_recorded"),
  day(6, "not_recorded"),
];

function renderView(
  options: {
    current?: CurrentAssignment;
    days?: DerivedStatsDay[];
    status?: "idle" | "loading" | "ready" | "error";
    error?: string;
    onToggle?: (item: CurrentAssignment["checklist_items"][number], checked: boolean) => void;
  } = {},
) {
  const onToggle = options.onToggle ?? vi.fn();
  const current = options.current ?? assignment();
  render(
    <Reshaped theme="slate">
      <StickerAssignmentView
        displayName="Alex"
        assignment={current}
        weekNumber={48}
        week={week(options.days ?? baseDays, current)}
        statsStatus={options.status ?? "ready"}
        statsError={options.error ?? ""}
        onRetryStats={vi.fn()}
        savingItemId={null}
        saveError=""
        onToggle={onToggle}
      />
    </Reshaped>,
  );
  return { onToggle };
}

describe("Sticker Club v2 view", () => {
  it("maps the week count, rail states, and all-done stamp", () => {
    renderView({
      current: assignment({
        checklist_items: [
          { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: true },
          { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: true },
          { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: true },
        ],
        is_complete: true,
      }),
    });

    expect(screen.getByRole("status")).toHaveTextContent("STICKER 2 OF 7");
    expect(screen.getByText("Sticker earned.")).toBeInTheDocument();
    const rail = screen.getByRole("list", { name: "This week's stickers" });
    expect(rail).toBeInTheDocument();
    expect(screen.getByLabelText("Wednesday, complete, today")).toBeInTheDocument();
    expect(within(rail).getAllByText("DONE")).toHaveLength(2);
    expect(within(rail).getByText("PART")).toBeInTheDocument();
    expect(within(rail).getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText(/leaderboard|rank/i)).not.toBeInTheDocument();
  });

  it("does not show the stamp before the day is complete and toggles jobs", () => {
    const current = assignment({
      checklist_items: [
        { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: true },
        { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: true },
        { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: false },
      ],
      is_complete: false,
    });
    const { onToggle } = renderView({ current });

    expect(screen.queryByText(/STICKER .* OF 7/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Wednesday, incomplete, today")).toBeInTheDocument();
    expect(screen.getByText("NEXT")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Take out trash" }));
    expect(onToggle).toHaveBeenCalledWith(
      expect.objectContaining({ id: 13 }),
      true,
    );
  });

  it("shows a placeholder count and non-blocking error when stats fail", () => {
    renderView({
      status: "error",
      error: "Stats service unavailable",
    });

    expect(screen.getByText("Sticker count unavailable")).toBeInTheDocument();
    expect(screen.getByText("Stats service unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kitchen" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Wipe counters" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("labels the header count as N of 7 this week and never fabricates zero", () => {
    const { rerender } = render(
      <StickerHeaderCount count={3} status="ready" />,
    );
    expect(screen.getByLabelText("3 of 7 this week")).toHaveTextContent("3");
    expect(screen.getByText("OF 7 STICKERS")).toBeInTheDocument();

    rerender(<StickerHeaderCount count={null} status="error" />);
    expect(screen.getByLabelText("Sticker count unavailable")).toHaveTextContent("—");
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
