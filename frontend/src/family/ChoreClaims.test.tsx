import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DailyChoreClaim } from "./api";
import { ChoreClaims } from "./ChoreClaims";

const AVAILABLE_CHORE = {
  id: 3,
  name: "Bathroom",
  description: "Scrub the bathroom",
  weight: 2,
  assigned_to: null,
};

const CLAIM: DailyChoreClaim = {
  id: 7,
  family_member_id: 1,
  chore_id: 3,
  claim_date: "2026-11-25",
  week_start: "2026-11-23",
  week_end: "2026-11-29",
  chore_name: "Bathroom",
  chore_description: "Scrub the bathroom",
  chore_weight: 2,
  claimed_at: "2026-11-25T18:04:12Z",
  is_completed: false,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderClaims(onStatsChange: () => void = () => undefined) {
  return render(
    <Reshaped theme="slate">
      <ChoreClaims familyMemberId={1} onStatsChange={onStatsChange} />
    </Reshaped>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ChoreClaims", () => {
  it("shows a loading state while extra chores are fetched", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    renderClaims();

    expect(
      screen.getByRole("progressbar", { name: "Loading available chores" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("shows an empty availability state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/available-chores")) {
          return jsonResponse({ claim_date: "2026-11-25", chores: [] });
        }
        if (url.endsWith("/claimed-chores")) {
          return jsonResponse({ claim_date: "2026-11-25", claims: [] });
        }
        return jsonResponse({ detail: "Not found" }, 404);
      }),
    );

    renderClaims();

    expect(
      await screen.findByText("No extra chores available right now."),
    ).toBeInTheDocument();
  });

  it("claims a chore and refreshes both lists", async () => {
    let availableGets = 0;
    let claimedGets = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.endsWith("/available-chores") && method === "GET") {
          availableGets += 1;
          return jsonResponse({
            claim_date: "2026-11-25",
            chores: availableGets === 1 ? [AVAILABLE_CHORE] : [],
          });
        }
        if (url.endsWith("/claimed-chores") && method === "GET") {
          claimedGets += 1;
          return jsonResponse({
            claim_date: "2026-11-25",
            claims: claimedGets === 1 ? [] : [CLAIM],
          });
        }
        if (url.endsWith("/claimed-chores") && method === "POST") {
          return jsonResponse(CLAIM, 201);
        }
        return jsonResponse({ detail: "Not found" }, 404);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const onStatsChange = vi.fn();
    renderClaims(onStatsChange);

    expect(await screen.findByText("Bathroom")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Claim" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === "/api/family-members/1/claimed-chores" &&
            init?.method === "POST" &&
            init.body === JSON.stringify({ chore_id: 3 }),
        ),
      ).toBe(true);
    });

    const availableSection = screen.getByRole("region", {
      name: "Available today",
    });
    await waitFor(() => {
      expect(within(availableSection).queryByText("Bathroom")).toBeNull();
    });
    expect(
      await screen.findByText("No extra chores available right now."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Claim" })).toBeNull();

    const claimedSection = screen.getByRole("region", {
      name: "Claimed today",
    });
    expect(within(claimedSection).getByText("Bathroom")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "Mark done" }),
    ).toBeInTheDocument();
    expect(availableGets).toBe(2);
    expect(claimedGets).toBe(2);
    expect(onStatsChange).toHaveBeenCalled();
  });

  it("shows a friendly conflict message and refreshes both lists on 409", async () => {
    let availableGets = 0;
    const detail = "Chore has already been claimed for this day";
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.endsWith("/available-chores") && method === "GET") {
          availableGets += 1;
          return jsonResponse({
            claim_date: "2026-11-25",
            chores: [AVAILABLE_CHORE],
          });
        }
        if (url.endsWith("/claimed-chores") && method === "GET") {
          return jsonResponse({ claim_date: "2026-11-25", claims: [] });
        }
        if (url.endsWith("/claimed-chores") && method === "POST") {
          return jsonResponse({ detail }, 409);
        }
        return jsonResponse({ detail: "Not found" }, 404);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const onStatsChange = vi.fn();
    renderClaims(onStatsChange);

    fireEvent.click(await screen.findByRole("button", { name: "Claim" }));

    const message = await screen.findByText(/no longer available to claim/i);
    expect(message).toHaveTextContent("updated list");
    expect(message).toHaveTextContent(detail);
    expect(onStatsChange).not.toHaveBeenCalled();

    await waitFor(() => expect(availableGets).toBeGreaterThanOrEqual(2));
    const claimedGetCount = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url).endsWith("/claimed-chores") &&
        (init?.method ?? "GET").toUpperCase() === "GET",
    ).length;
    expect(claimedGetCount).toBeGreaterThanOrEqual(2);
  });

  it("marks a claimed chore done and refreshes derived stats", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.endsWith("/available-chores") && method === "GET") {
          return jsonResponse({ claim_date: "2026-11-25", chores: [] });
        }
        if (url.endsWith("/claimed-chores") && method === "GET") {
          return jsonResponse({ claim_date: "2026-11-25", claims: [CLAIM] });
        }
        if (url.endsWith("/claimed-chores/7/completion") && method === "PUT") {
          return jsonResponse({ ...CLAIM, is_completed: true });
        }
        return jsonResponse({ detail: "Not found" }, 404);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const onStatsChange = vi.fn();
    renderClaims(onStatsChange);

    const checkbox = await screen.findByRole("checkbox", {
      name: "Mark done",
    });
    fireEvent.click(checkbox);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) ===
              "/api/family-members/1/claimed-chores/7/completion" &&
            init?.method === "PUT" &&
            init.body === JSON.stringify({ is_completed: true }),
        ),
      ).toBe(true);
    });
    expect(onStatsChange).toHaveBeenCalled();
    expect(
      screen.getByRole("checkbox", { name: "Mark done" }),
    ).toBeChecked();
  });

  it("labels a claimable chore that belonged to another child", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/available-chores")) {
          return jsonResponse({
            claim_date: "2026-11-25",
            chores: [{ ...AVAILABLE_CHORE, assigned_to: "Sam" }],
          });
        }
        if (url.endsWith("/claimed-chores")) {
          return jsonResponse({ claim_date: "2026-11-25", claims: [] });
        }
        return jsonResponse({ detail: "Not found" }, 404);
      }),
    );

    renderClaims();

    expect(
      await screen.findByText("Sam's unfinished chore"),
    ).toBeInTheDocument();
  });

  it("shows a load error and retries", async () => {
    let attempts = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/available-chores")) {
        attempts += 1;
        return attempts === 1
          ? jsonResponse({ detail: "Claims service unavailable" }, 500)
          : jsonResponse({ claim_date: "2026-11-25", chores: [] });
      }
      if (url.endsWith("/claimed-chores")) {
        return jsonResponse({ claim_date: "2026-11-25", claims: [] });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderClaims();

    expect(
      await screen.findByText("Claims service unavailable"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByText("No extra chores available right now."),
    ).toBeInTheDocument();
    expect(attempts).toBe(2);
  });
});
