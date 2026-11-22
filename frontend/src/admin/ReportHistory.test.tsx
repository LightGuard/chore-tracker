import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { Reshaped } from "reshaped";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReportHistory } from "./ReportHistory";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
      handler(String(input), init),
    ),
  );
}

function renderHistory(onSessionExpired = vi.fn()) {
  return render(
    <Reshaped theme="slate">
      <MemoryRouter>
        <ReportHistory onSessionExpired={onSessionExpired} />
      </MemoryRouter>
    </Reshaped>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const reports = [
  {
    id: 2,
    week_start: "2026-11-16",
    week_end: "2026-11-22",
    generated_at: "2026-11-23T10:00:00Z",
    summary: {
      family_member_count: 3,
      total_days: 21,
      completed_days: 11,
      incomplete_days: 10,
    },
  },
  {
    id: 1,
    week_start: "2026-11-09",
    week_end: "2026-11-15",
    generated_at: "2026-11-16T10:00:00Z",
    summary: {
      family_member_count: 2,
      total_days: 14,
      completed_days: 14,
      incomplete_days: 0,
    },
  },
];

describe("weekly report history", () => {
  it("lists persisted reports newest first with week, generation, and totals", async () => {
    installFetch(() => jsonResponse(reports));

    renderHistory();

    expect(
      await screen.findByRole("heading", {
        name: "Report history",
      }),
    ).toBeInTheDocument();
    const newest = screen.getByRole("heading", {
      name: "Nov 16 – 22, 2026",
    });
    const older = screen.getByRole("heading", {
      name: "Nov 9 – 15, 2026",
    });
    expect(newest).toBeInTheDocument();
    expect(older).toBeInTheDocument();
    expect(screen.getByText("11 / 21 days")).toBeInTheDocument();
    expect(screen.getByText("14 / 14 days")).toBeInTheDocument();
    expect(screen.getByText("3 children · 10 incomplete days")).toBeInTheDocument();

    const link = screen.getByRole("link", {
      name: "View report for Nov 16 – 22, 2026",
    });
    expect(link).toHaveAttribute("href", "/admin/reports/2026-11-16");
    expect(screen.getByText(/Mon, Nov 23, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Mon, Nov 16, 2026/)).toBeInTheDocument();
  });

  it("shows a clear empty state when no reports have been generated", async () => {
    installFetch(() => jsonResponse([]));

    renderHistory();

    expect(
      await screen.findByText("No weekly reports yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Reports are created after a Monday–Sunday week ends/),
    ).toBeInTheDocument();
  });

  it("expires the administrator session when report history is unauthorized", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Authentication required" }, 401),
    );
    const onSessionExpired = vi.fn();

    renderHistory(onSessionExpired);

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });
});
