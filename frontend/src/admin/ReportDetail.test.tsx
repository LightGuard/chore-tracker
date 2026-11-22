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
import type { WeeklyReportDay, WeeklyReportEntry } from "./api";

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
  },
  {
    id: 2,
    family_member_name: "Jordan",
    chore_name: "Bathroom",
    chore_description: "Clean the bathroom",
    completed_days: 0,
    incomplete_days: 7,
    days: daysFor(0),
  },
  {
    id: 3,
    family_member_name: "Morgan",
    chore_name: "Laundry",
    chore_description: "Wash the clothes",
    completed_days: 5,
    incomplete_days: 2,
    days: daysFor(5),
  },
  {
    id: 4,
    family_member_name: "Riley",
    chore_name: "Yard",
    chore_description: "Maintain the yard",
    completed_days: 4,
    incomplete_days: 3,
    days: daysFor(4),
  },
  {
    id: 5,
    family_member_name: "Sam",
    chore_name: "Kitchen",
    chore_description: "Clean the kitchen",
    completed_days: 2,
    incomplete_days: 5,
    days: daysFor(2),
  },
  {
    id: 6,
    family_member_name: "Taylor",
    chore_name: "Bathroom",
    chore_description: "Clean the bathroom",
    completed_days: 3,
    incomplete_days: 4,
    days: daysFor(3),
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
});
