import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FamilyCompletionHistory } from "./FamilyCompletionHistory";
import type { CompletionHistoryRecord } from "./api";

const RECORDS: CompletionHistoryRecord[] = [
  {
    assignment_id: 10,
    week_start: "2026-11-16",
    week_end: "2026-11-22",
    chore_name: "Kitchen",
    chore_description: "Wipe and sweep.",
    chore_weight: 1,
    completion_date: "2026-11-22",
    completion_status: "complete",
  },
  {
    assignment_id: 10,
    week_start: "2026-11-16",
    week_end: "2026-11-22",
    chore_name: "Kitchen",
    chore_description: "Wipe and sweep.",
    chore_weight: 1,
    completion_date: "2026-11-21",
    completion_status: "incomplete",
  },
  {
    assignment_id: 10,
    week_start: "2026-11-16",
    week_end: "2026-11-22",
    chore_name: "Kitchen",
    chore_description: "Wipe and sweep.",
    chore_weight: 1,
    completion_date: "2026-11-20",
    completion_status: "not_yet_recorded",
  },
  {
    assignment_id: 9,
    week_start: "2026-11-09",
    week_end: "2026-11-15",
    chore_name: "Yard",
    chore_description: "Maintain the yard.",
    chore_weight: 3,
    completion_date: "2026-11-10",
    completion_status: "complete",
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function historyPage(items = RECORDS, total = 14) {
  return jsonResponse({ items, total, limit: 50, offset: 0 });
}

function installFetch(
  handler: (input: RequestInfo | URL) => Promise<Response>,
) {
  const fetchMock = vi.fn(handler);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderHistory(today?: string | null) {
  return render(
    <Reshaped theme="slate">
      <FamilyCompletionHistory
        familyMemberId={1}
        displayName="Alex"
        today={today}
      />
    </Reshaped>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("family completion history", () => {
  it("shows a loading state while history is fetched", () => {
    installFetch(() => new Promise<Response>(() => undefined));

    renderHistory();

    expect(
      screen.getByRole("progressbar", { name: "Loading completion history" }),
    ).toBeInTheDocument();
  });

  it("groups history by week and labels every completion state", async () => {
    installFetch(async () => historyPage());

    renderHistory();

    expect(
      await screen.findByRole("heading", {
        name: "Completion history for Alex",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Kitchen")).toBeInTheDocument();
    expect(screen.getByText("Yard")).toBeInTheDocument();
    expect(
      screen.getByText("Week of Nov 16, 2026 – Nov 22, 2026"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Week of Nov 9, 2026 – Nov 15, 2026"),
    ).toBeInTheDocument();

    const completeDay = screen.getByText("Sunday, Nov 22, 2026");
    expect(completeDay).toHaveAttribute("datetime", "2026-11-22");
    expect(screen.getAllByText("Complete")).toHaveLength(2);
    expect(screen.getByText("Incomplete")).toBeInTheDocument();
    expect(screen.getByText("Not yet recorded")).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Kitchen daily records" }),
    ).toBeInTheDocument();
  });

  it("marks future dates as upcoming while past and today stay not yet recorded", async () => {
    const week: CompletionHistoryRecord[] = [
      {
        assignment_id: 11,
        week_start: "2026-11-23",
        week_end: "2026-11-29",
        chore_name: "Bath",
        chore_description: "Wipe the tub.",
        chore_weight: 1,
        completion_date: "2026-11-24",
        completion_status: "not_yet_recorded",
      },
      {
        assignment_id: 11,
        week_start: "2026-11-23",
        week_end: "2026-11-29",
        chore_name: "Bath",
        chore_description: "Wipe the tub.",
        chore_weight: 1,
        completion_date: "2026-11-25",
        completion_status: "complete",
      },
      {
        assignment_id: 11,
        week_start: "2026-11-23",
        week_end: "2026-11-29",
        chore_name: "Bath",
        chore_description: "Wipe the tub.",
        chore_weight: 1,
        completion_date: "2026-11-26",
        completion_status: "incomplete",
      },
      {
        assignment_id: 11,
        week_start: "2026-11-23",
        week_end: "2026-11-29",
        chore_name: "Bath",
        chore_description: "Wipe the tub.",
        chore_weight: 1,
        completion_date: "2026-11-27",
        completion_status: "not_yet_recorded",
      },
      {
        assignment_id: 11,
        week_start: "2026-11-23",
        week_end: "2026-11-29",
        chore_name: "Bath",
        chore_description: "Wipe the tub.",
        chore_weight: 1,
        completion_date: "2026-11-28",
        completion_status: "not_yet_recorded",
      },
    ];
    function badgeTextFor(dayLabel: string): string | null {
      const row = screen.getByText(dayLabel).closest("li");
      return row?.textContent ?? null;
    }

    installFetch(async () => historyPage(week, week.length));

    renderHistory("2026-11-27");

    expect(
      await screen.findByRole("heading", {
        name: "Completion history for Alex",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Week of Nov 23, 2026 – Nov 29, 2026"),
    ).toBeInTheDocument();

    expect(badgeTextFor("Tuesday, Nov 24, 2026")).toContain(
      "Not yet recorded",
    );
    expect(badgeTextFor("Friday, Nov 27, 2026")).toContain("Not yet recorded");
    expect(badgeTextFor("Saturday, Nov 28, 2026")).toContain("Upcoming");
    expect(badgeTextFor("Wednesday, Nov 25, 2026")).toContain("Complete");
    expect(badgeTextFor("Thursday, Nov 26, 2026")).toContain("Incomplete");
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
  });

  it("shows an empty state when the child has no history", async () => {
    installFetch(async () => historyPage([], 0));

    renderHistory();

    expect(
      await screen.findByText("No completion history yet"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Alex has no historical chore records/)).toBeInTheDocument();
  });

  it("shows an API error and retries the history request", async () => {
    let attempts = 0;
    installFetch(async () => {
      attempts += 1;
      return attempts === 1
        ? jsonResponse({ detail: "History service unavailable" }, 500)
        : historyPage();
    });

    renderHistory();

    expect(
      await screen.findByText("History service unavailable"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", {
        name: "Completion history for Alex",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Kitchen")).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("loads the next page of history", async () => {
    const secondRecord: CompletionHistoryRecord = {
      ...RECORDS[0],
      assignment_id: 8,
      week_start: "2026-11-02",
      week_end: "2026-11-08",
      chore_name: "Laundry",
      completion_date: "2026-11-06",
      completion_status: "complete",
    };
    const fetchMock = installFetch(async (input) => {
      const url = String(input);
      return url.includes("offset=0")
        ? jsonResponse({ items: RECORDS.slice(0, 3), total: 4, limit: 50, offset: 0 })
        : jsonResponse({
            items: [secondRecord],
            total: 4,
            limit: 50,
            offset: 3,
          });
    });

    renderHistory();

    expect(await screen.findByText("Kitchen")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more history" }));

    expect(await screen.findByText("Laundry")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("offset=3"))).toBe(
      true,
    );
  });
});
