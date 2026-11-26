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
    chore_weight: 1,
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
  it("maps the weighted week count, rail states, and all-done stamp", () => {
    renderView();

    expect(screen.getByRole("status")).toHaveTextContent("2 STICKERS");
    expect(screen.getByText("Sticker earned.")).toBeInTheDocument();
    expect(
      screen.getByText("One sticker for each finished day."),
    ).toBeInTheDocument();
    expect(screen.getByText("2 of 7 days")).toBeInTheDocument();
    const rail = screen.getByRole("list", { name: "This week's stickers" });
    expect(rail).toBeInTheDocument();
    expect(screen.getByLabelText("Wednesday, complete, 1 sticker, today")).toBeInTheDocument();
    expect(within(rail).getAllByText("DONE")).toHaveLength(2);
    expect(within(rail).getByText("PART")).toBeInTheDocument();
    expect(within(rail).getAllByText("+1")).toHaveLength(2);
    expect(within(rail).getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText(/leaderboard|rank/i)).not.toBeInTheDocument();
  });

  it("multiplies weighted stickers per complete day", () => {
    const current = assignment({ chore_weight: 2 });
    renderView({ current });

    expect(screen.getByRole("status")).toHaveTextContent("4 STICKERS");
    expect(screen.getByText("2 stickers per finished day")).toBeInTheDocument();
    expect(
      screen.getByText("2 stickers for each finished day."),
    ).toBeInTheDocument();
    const rail = screen.getByRole("list", { name: "This week's stickers" });
    expect(within(rail).getAllByText("+2")).toHaveLength(2);
    expect(screen.getByLabelText("Monday, complete, 2 stickers")).toBeInTheDocument();
    expect(screen.getByLabelText("Wednesday, complete, 2 stickers, today")).toBeInTheDocument();
    expect(screen.getByText("2 of 7 days")).toBeInTheDocument();
  });

  it("mints no stickers for a weight-0 chore", () => {
    renderView({ current: assignment({ chore_weight: 0 }) });

    expect(screen.getByRole("status")).toHaveTextContent("0 STICKERS");
    expect(screen.getByText("No sticker weight")).toBeInTheDocument();
    expect(
      screen.getByText("This chore mints no stickers."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "This chore's weight is 0, so finished days mint no stickers. A new week starts with a clean sheet.",
      ),
    ).toBeInTheDocument();
    const rail = screen.getByRole("list", { name: "This week's stickers" });
    expect(within(rail).getAllByText("DONE")).toHaveLength(2);
    expect(within(rail).queryByText(/^\+/)).not.toBeInTheDocument();
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

    expect(screen.queryByText(/STICKERS$/)).not.toBeInTheDocument();
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

    render(
      <StickerHeaderCount count={null} status="error" />,
    );
    expect(
      screen.getByRole("status", { name: "Sticker count unavailable" }),
    ).toHaveTextContent("—");
    expect(screen.getByText("Sticker count unavailable")).toBeInTheDocument();
    expect(screen.getByText("Stats service unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kitchen" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Wipe counters" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("labels the header count in stickers this week and never fabricates zero", () => {
    const { rerender } = render(
      <StickerHeaderCount count={3} status="ready" />,
    );
    expect(screen.getByLabelText("3 stickers this week")).toHaveTextContent("3");
    expect(screen.getByText("STICKERS THIS WEEK")).toBeInTheDocument();

    rerender(<StickerHeaderCount count={1} status="ready" />);
    expect(screen.getByLabelText("1 sticker this week")).toHaveTextContent("1");
    expect(screen.getByText("STICKER THIS WEEK")).toBeInTheDocument();

    rerender(<StickerHeaderCount count={null} status="ready" />);
    expect(
      screen.getByRole("status", { name: "Sticker count unavailable" }),
    ).toHaveTextContent("—");

    rerender(<StickerHeaderCount count={null} status="error" />);
    expect(screen.getByLabelText("Sticker count unavailable")).toHaveTextContent("—");
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
