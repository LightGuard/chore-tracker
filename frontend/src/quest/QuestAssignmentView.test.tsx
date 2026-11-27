import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CurrentAssignment, DerivedStats } from "../family/api";
import { QuestAssignmentView } from "./QuestAssignmentView";

function stats(overrides: Partial<DerivedStats> = {}): DerivedStats {
  return {
    family_member_id: 1,
    display_name: "Alex",
    as_of: "2026-11-25",
    timezone: "America/Denver",
    lifetime: {
      completed_checklist_items: 124,
      xp: 1240,
      complete_days: 31,
      current_streak: 4,
    },
    current_week: {
      week_start: "2026-11-23",
      week_end: "2026-11-29",
      completed_checklist_items: 38,
      xp: 380,
      complete_days: 3,
      days: [
        {
          date: "2026-11-23",
          completed_checklist_items: 3,
          total_checklist_items: 3,
          state: "complete",
        },
        {
          date: "2026-11-24",
          completed_checklist_items: 2,
          total_checklist_items: 3,
          state: "incomplete",
        },
        {
          date: "2026-11-25",
          completed_checklist_items: 0,
          total_checklist_items: 3,
          state: "not_recorded",
        },
      ],
    },
    household: {
      active_players: 4,
      weekly_standings: [
        {
          family_member_id: 3,
          display_name: "Riley",
          completed_checklist_items: 42,
          xp: 420,
          complete_days: 5,
          current_streak: 5,
        },
        {
          family_member_id: 1,
          display_name: "Alex",
          completed_checklist_items: 38,
          xp: 380,
          complete_days: 3,
          current_streak: 4,
        },
        {
          family_member_id: 4,
          display_name: "Avery",
          completed_checklist_items: 32,
          xp: 320,
          complete_days: 2,
          current_streak: 2,
        },
        {
          family_member_id: 2,
          display_name: "Sam",
          completed_checklist_items: 24,
          xp: 240,
          complete_days: 1,
          current_streak: 1,
        },
      ],
      xp_rankings: [
        {
          family_member_id: 3,
          display_name: "Riley",
          total_xp: 1240,
          rank: 1,
        },
        {
          family_member_id: 1,
          display_name: "Alex",
          total_xp: 1240,
          rank: 1,
        },
        {
          family_member_id: 4,
          display_name: "Avery",
          total_xp: 720,
          rank: 3,
        },
        {
          family_member_id: 2,
          display_name: "Sam",
          total_xp: 610,
          rank: 4,
        },
      ],
    },
    ...overrides,
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
      { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: false },
      { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: false },
    ],
    is_complete: false,
    ...overrides,
  };
}

function renderView(overrides: {
  stats?: DerivedStats | null;
  assignment?: CurrentAssignment;
  status?: "idle" | "loading" | "ready" | "error";
  error?: string;
  onToggle?: (item: CurrentAssignment["checklist_items"][number], checked: boolean) => void;
}) {
  const onToggle = overrides.onToggle ?? vi.fn();
  render(
    <Reshaped theme="slate">
      <QuestAssignmentView
        displayName="Alex"
        assignment={overrides.assignment ?? assignment()}
        weekNumber={48}
        stats={overrides.stats === undefined ? stats() : overrides.stats}
        statsStatus={overrides.status ?? "ready"}
        statsError={overrides.error ?? ""}
        onRetryStats={vi.fn()}
        savingItemId={null}
        saveError=""
        onToggle={onToggle}
      />
    </Reshaped>,
  );
  return { onToggle };
}

afterEach(cleanup);

describe("Quest assignment view", () => {
  it("renders XP, level progress, streak, weekly days, and achievement rank", () => {
    renderView({});

    expect(screen.getByRole("heading", { name: "Kitchen" })).toBeInTheDocument();
    expect(screen.getByText("1,240 / 1,500 XP")).toBeInTheDocument();
    expect(screen.getByText("380 XP THIS WEEK")).toBeInTheDocument();
    expect(screen.getByText("LVL 03")).toBeInTheDocument();
    expect(screen.getByText("4-DAY STREAK")).toBeInTheDocument();
    expect(screen.getByText("XP RANK")).toBeInTheDocument();
    expect(screen.getByText("ACHIEVEMENT RANK")).toBeInTheDocument();
    expect(screen.getByText("YOU'RE #1")).toBeInTheDocument();
    expect(screen.getByLabelText("XP rank 1 of 4")).toHaveTextContent("#01");
    expect(screen.getByRole("progressbar", { name: "Progress to next level" })).toHaveAttribute(
      "aria-valuenow",
      "240",
    );
    expect(screen.getByText(/3 \/ 7/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Wipe counters" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Sweep floor" })).not.toBeChecked();
  });

  it("scales each objective's XP label by the chore weight", () => {
    renderView({ assignment: assignment({ chore_weight: 3 }) });
    expect(screen.getAllByText("+30 XP")).toHaveLength(3);
    expect(screen.getByText(/\+90 XP TODAY/)).toBeInTheDocument();
    cleanup();

    renderView({ assignment: assignment({ chore_weight: 0 }) });
    expect(screen.getAllByText("+0 XP")).toHaveLength(3);
    expect(screen.getByText(/\+0 XP TODAY/)).toBeInTheDocument();
    cleanup();

    renderView({ assignment: assignment({ chore_weight: 1 }) });
    expect(screen.getAllByText("+10 XP")).toHaveLength(3);
    expect(screen.getByText(/\+30 XP TODAY/)).toBeInTheDocument();
  });

  it("shows the family-wide achievement rank, not the weekly standings position", () => {
    renderView({
      stats: stats({
        household: {
          active_players: 4,
          weekly_standings: [
            {
              family_member_id: 1,
              display_name: "Alex",
              completed_checklist_items: 42,
              xp: 420,
              complete_days: 5,
              current_streak: 5,
            },
            {
              family_member_id: 3,
              display_name: "Riley",
              completed_checklist_items: 38,
              xp: 380,
              complete_days: 3,
              current_streak: 4,
            },
            {
              family_member_id: 4,
              display_name: "Avery",
              completed_checklist_items: 32,
              xp: 320,
              complete_days: 2,
              current_streak: 2,
            },
            {
              family_member_id: 2,
              display_name: "Sam",
              completed_checklist_items: 24,
              xp: 240,
              complete_days: 1,
              current_streak: 1,
            },
          ],
          xp_rankings: [
            {
              family_member_id: 3,
              display_name: "Riley",
              total_xp: 1240,
              rank: 1,
            },
            {
              family_member_id: 4,
              display_name: "Avery",
              total_xp: 980,
              rank: 2,
            },
            {
              family_member_id: 1,
              display_name: "Alex",
              total_xp: 720,
              rank: 3,
            },
            {
              family_member_id: 2,
              display_name: "Sam",
              total_xp: 610,
              rank: 4,
            },
          ],
        },
      }),
    });

    expect(screen.getByLabelText("XP rank 3 of 4")).toHaveTextContent("#03");
    expect(screen.getByText("520 XP TO #1")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("XP rank 1 of 4"),
    ).not.toBeInTheDocument();
  });

  it("shows an unavailable gap when the selected child has no achievement rank", () => {
    renderView({
      stats: stats({
        household: {
          active_players: 2,
          weekly_standings: [],
          xp_rankings: [
            {
              family_member_id: 3,
              display_name: "Riley",
              total_xp: 240,
              rank: 1,
            },
          ],
        },
      }),
    });

    expect(screen.getByLabelText("XP rank unknown of 2")).toHaveTextContent("#--");
    expect(screen.getByText("RANK UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText(/XP TO #1/)).not.toBeInTheDocument();
  });

  it("shows a clear, non-color-only all-done state and toggles objectives", () => {
    const { onToggle } = renderView({
      assignment: assignment({
        checklist_items: [
          { id: 11, label: "Wipe counters", position: 0, is_required: true, is_completed: true },
          { id: 12, label: "Sweep floor", position: 1, is_required: true, is_completed: true },
          { id: 13, label: "Take out trash", position: 2, is_required: true, is_completed: true },
        ],
        is_complete: true,
      }),
    });

    expect(screen.getByRole("status")).toHaveTextContent("QUEST CLEAR");
    expect(screen.getByText(/Every objective is done today/)).toBeInTheDocument();
    expect(screen.getByText("ACHIEVEMENT RANK")).toBeInTheDocument();
    expect(screen.queryByText(/shop|reward|season/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Sweep floor" }));
    expect(onToggle).toHaveBeenCalledWith(
      expect.objectContaining({ id: 12, label: "Sweep floor" }),
      false,
    );
  });

  it("keeps the checklist usable when stats fail and exposes a retry", () => {
    const onRetry = vi.fn();
    render(
      <Reshaped theme="slate">
        <QuestAssignmentView
          displayName="Alex"
          assignment={assignment()}
          weekNumber={48}
          stats={null}
          statsStatus="error"
          statsError="Quest stats service unavailable"
          onRetryStats={onRetry}
          savingItemId={null}
          saveError=""
          onToggle={vi.fn()}
        />
      </Reshaped>,
    );

    expect(screen.getByText("Quest stats service unavailable")).toBeInTheDocument();
    expect(screen.getByText("Progress unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kitchen" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sweep floor" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("scales today's XP chip by the chore weight", () => {
    renderView({ assignment: assignment({ chore_weight: 3 }) });
    expect(screen.getByText("+90 XP TODAY")).toBeInTheDocument();
    cleanup();

    renderView({ assignment: assignment({ chore_weight: 0 }) });
    expect(screen.getByText("+0 XP TODAY")).toBeInTheDocument();
    cleanup();

    renderView({ assignment: assignment({ chore_weight: 1 }) });
    expect(screen.getByText("+30 XP TODAY")).toBeInTheDocument();
  });
});
