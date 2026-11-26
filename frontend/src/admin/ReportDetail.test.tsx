import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { Reshaped } from "reshaped";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReportDetail } from "./ReportDetail";
import type {
  WeeklyReportDay,
  WeeklyReportEntry,
  WeeklyReportReward,
} from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) =>
      handler(String(input), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const WEEK_START = "2026-11-16";
const WEEK_END = "2026-11-22";
const DAYS = Array.from({ length: 7 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 10, 16 + index));
  return date.toISOString().slice(0, 10);
});

function daysFor(completed: number): WeeklyReportDay[] {
  return DAYS.map((date, index) => ({
    date,
    status: index < completed ? "complete" : "incomplete",
  }));
}

const entries: WeeklyReportEntry[] = [
  {
    id: 1,
    family_member_name: "Alex",
    chore_name: "Kitchen",
    chore_description: "Clean the kitchen",
    completed_days: 7,
    incomplete_days: 0,
    days: daysFor(7),
    reward: null,
  },
  {
    id: 2,
    family_member_name: "Jordan",
    chore_name: "Bathroom",
    chore_description: "Clean the bathroom",
    completed_days: 0,
    incomplete_days: 7,
    days: daysFor(0),
    reward: null,
  },
  {
    id: 3,
    family_member_name: "Morgan",
    chore_name: "Laundry",
    chore_description: "Wash the clothes",
    completed_days: 5,
    incomplete_days: 2,
    days: daysFor(5),
    reward: null,
  },
  {
    id: 4,
    family_member_name: "Riley",
    chore_name: "Yard",
    chore_description: "Maintain the yard",
    completed_days: 4,
    incomplete_days: 3,
    days: daysFor(4),
    reward: null,
  },
  {
    id: 5,
    family_member_name: "Sam",
    chore_name: "Kitchen",
    chore_description: "Clean the kitchen",
    completed_days: 2,
    incomplete_days: 5,
    days: daysFor(2),
    reward: null,
  },
  {
    id: 6,
    family_member_name: "Taylor",
    chore_name: "Bathroom",
    chore_description: "Clean the bathroom",
    completed_days: 3,
    incomplete_days: 4,
    days: daysFor(3),
    reward: null,
  },
];

const reportHeader = {
  id: 42,
  week_start: WEEK_START,
  week_end: WEEK_END,
  generated_at: "2026-11-23T10:00:00Z",
  summary: {
    family_member_count: 6,
    total_days: 42,
    completed_days: 21,
    incomplete_days: 21,
  },
};

const ALEX_REWARD: WeeklyReportReward = {
  rewarded_at: "2026-11-26T15:30:00Z",
  rewarded_by: {
    administrator_id: 1,
    email: "admin@example.test",
  },
};

function reportResponse(reportEntries: WeeklyReportEntry[]) {
  return jsonResponse({
    ...reportHeader,
    entries: reportEntries,
    total: reportEntries.length,
    limit: 5,
    offset: 0,
  });
}

function renderDetail(onSessionExpired = vi.fn()) {
  return render(
    <Reshaped theme="slate">
      <MemoryRouter>
        <ReportDetail
          weekStart={WEEK_START}
          onSessionExpired={onSessionExpired}
        />
      </MemoryRouter>
    </Reshaped>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("weekly report detail", () => {
  it("renders persisted summary, daily statuses, rows, and pagination", async () => {
    const fetchMock = installFetch((url) => {
      const requestUrl = new URL(url, "http://localhost");
      const offset = Number(requestUrl.searchParams.get("offset") ?? 0);
      const limit = Number(requestUrl.searchParams.get("limit") ?? 25);
      return jsonResponse({
        ...reportHeader,
        entries: entries.slice(offset, offset + limit),
        total: entries.length,
        limit,
        offset,
      });
    });

    renderDetail();

    expect(
      await screen.findByRole("heading", { name: "Nov 16 – 22, 2026" }),
    ).toBeInTheDocument();
    expect(screen.getByText("of 42 child-day slots")).toBeInTheDocument();
    expect(
      screen.getByText("Showing 1–5 of 6 entries"),
    ).toBeInTheDocument();

    const table = screen.getByRole("table", {
      name: "Report entries for Nov 16 – 22, 2026",
    });
    const alex = within(table).getByRole("row", {
      name: "Report entry for Alex",
    });
    expect(within(alex).getByText("Kitchen")).toBeInTheDocument();
    expect(within(alex).getByLabelText("2026-11-16: Complete")).toBeInTheDocument();
    expect(within(alex).getByLabelText("2026-11-22: Complete")).toBeInTheDocument();
    expect(within(alex).getByText("Complete")).toBeInTheDocument();

    const riley = within(table).getByRole("row", {
      name: "Report entry for Riley",
    });
    expect(within(riley).getByLabelText("2026-11-19: Complete")).toBeInTheDocument();
    expect(
      within(riley).getByLabelText("2026-11-20: Incomplete"),
    ).toBeInTheDocument();
    expect(within(riley).getByText("3 incomplete")).toBeInTheDocument();

    expect(screen.queryByRole("row", { name: "Report entry for Taylor" }))
      .not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(
      await screen.findByText("Showing 6–6 of 6 entries"),
    ).toBeInTheDocument();
    const taylor = screen.getByRole("row", {
      name: "Report entry for Taylor",
    });
    expect(within(taylor).getByText("Bathroom")).toBeInTheDocument();
    expect(
      screen.queryByRole("row", { name: "Report entry for Alex" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("offset=5"),
      ),
    ).toBe(true);
  });

  it("shows an explicit empty state for a report with no entries", async () => {
    installFetch(() =>
      jsonResponse({
        ...reportHeader,
        summary: {
          family_member_count: 0,
          total_days: 0,
          completed_days: 0,
          incomplete_days: 0,
        },
        entries: [],
        total: 0,
        limit: 5,
        offset: 0,
      }),
    );

    renderDetail();

    expect(
      await screen.findByText("This report has no entries"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders a not-found state for a missing report", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Weekly report was not found" }, 404),
    );

    renderDetail();

    expect(await screen.findByText("Report not found")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "← All weekly reports" }),
    ).toHaveAttribute("href", "/admin/reports");
  });

  it("expires the administrator session when the report is unauthorized", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Authentication required" }, 401),
    );
    const onSessionExpired = vi.fn();

    renderDetail(onSessionExpired);

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });

  it("marks an entry rewarded and shows the persisted audit details", async () => {
    const fetchMock = installFetch((_url, init) => {
      if (init?.method === "PUT") return jsonResponse(ALEX_REWARD);
      return reportResponse(entries.slice(0, 5));
    });

    renderDetail();

    const table = await screen.findByRole("table", {
      name: "Report entries for Nov 16 – 22, 2026",
    });
    const alex = within(table).getByRole("row", {
      name: "Report entry for Alex",
    });
    expect(within(alex).getByText("Not rewarded")).toBeInTheDocument();

    fireEvent.click(
      within(alex).getByRole("button", { name: "Mark reward for Alex" }),
    );

    await waitFor(() =>
      expect(within(alex).getByText("Rewarded")).toBeInTheDocument(),
    );
    expect(
      within(alex).queryByRole("button", { name: "Mark reward for Alex" }),
    ).not.toBeInTheDocument();
    expect(
      within(alex).getByText("admin@example.test", { exact: false }),
    ).toBeInTheDocument();
    const rewardedAt = alex.querySelector("time");
    expect(rewardedAt?.getAttribute("datetime")).toBe(
      ALEX_REWARD.rewarded_at,
    );

    const putCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "PUT",
    );
    expect(String(putCall?.[0])).toContain(
      "/reports/2026-11-16/entries/1/reward",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Alex's reward was recorded.",
    );
    const jordan = within(table).getByRole("row", {
      name: "Report entry for Jordan",
    });
    expect(within(jordan).getByText("Not rewarded")).toBeInTheDocument();
  });

  it("shows a persisted reward without offering the action again", async () => {
    installFetch(() =>
      reportResponse(
        entries
          .slice(0, 5)
          .map((entry) =>
            entry.id === 1 ? { ...entry, reward: ALEX_REWARD } : entry,
          ),
      ),
    );

    renderDetail();

    const table = await screen.findByRole("table", {
      name: "Report entries for Nov 16 – 22, 2026",
    });
    const alex = within(table).getByRole("row", {
      name: "Report entry for Alex",
    });
    expect(within(alex).getByText("Rewarded")).toBeInTheDocument();
    expect(
      within(alex).getByText("admin@example.test", { exact: false }),
    ).toBeInTheDocument();
    expect(
      within(alex).queryByRole("button", { name: "Mark reward for Alex" }),
    ).not.toBeInTheDocument();
    const sam = within(table).getByRole("row", {
      name: "Report entry for Sam",
    });
    expect(
      within(sam).getByRole("button", { name: "Mark reward for Sam" }),
    ).toBeInTheDocument();
  });

  it("communicates a reward API failure without showing a false success", async () => {
    installFetch((_url, init) => {
      if (init?.method === "PUT") {
        return jsonResponse(
          { detail: "Weekly report entry was not found" },
          404,
        );
      }
      return reportResponse(entries.slice(0, 5));
    });

    renderDetail();

    const table = await screen.findByRole("table", {
      name: "Report entries for Nov 16 – 22, 2026",
    });
    const alex = within(table).getByRole("row", {
      name: "Report entry for Alex",
    });
    fireEvent.click(
      within(alex).getByRole("button", { name: "Mark reward for Alex" }),
    );

    expect(
      await screen.findByText("Couldn't record Alex's reward"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Weekly report entry was not found"),
    ).toBeInTheDocument();
    expect(within(alex).getByText("Not rewarded")).toBeInTheDocument();
    expect(within(alex).queryByText("Rewarded")).not.toBeInTheDocument();
    expect(
      within(alex).getByRole("button", { name: "Mark reward for Alex" }),
    ).toBeEnabled();
  });

  it("expires the session when marking a reward is unauthorized", async () => {
    installFetch((_url, init) => {
      if (init?.method === "PUT") {
        return jsonResponse({ detail: "Authentication required" }, 401);
      }
      return reportResponse(entries.slice(0, 5));
    });
    const onSessionExpired = vi.fn();

    renderDetail(onSessionExpired);

    const table = await screen.findByRole("table", {
      name: "Report entries for Nov 16 – 22, 2026",
    });
    const alex = within(table).getByRole("row", {
      name: "Report entry for Alex",
    });
    fireEvent.click(
      within(alex).getByRole("button", { name: "Mark reward for Alex" }),
    );

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });
});
