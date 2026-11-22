import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CurrentAssignment, FamilyMember } from "./api";
import { FamilyChorePage } from "./FamilyChorePage";

const MEMBERS: FamilyMember[] = [
  { id: 1, display_name: "Alex" },
  { id: 2, display_name: "Sam" },
];

function assignment(overrides: Partial<CurrentAssignment> = {}): CurrentAssignment {
  return {
    id: 10,
    family_member_id: 1,
    week_start: "2026-11-16",
    week_end: "2026-11-22",
    chore_name: "Kitchen",
    chore_description: "Wipe and sweep after dinner.",
    today: "2026-11-18",
    checklist_items: [
      { id: 11, label: "Wipe counters", position: 0, is_completed: false },
      { id: 12, label: "Sweep floor", position: 1, is_completed: false },
    ],
    is_complete: false,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  const fetchMock = vi.fn(handler);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <Reshaped theme="slate">
      <FamilyChorePage />
    </Reshaped>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("family chore page", () => {
  it("shows a loading state while family members are fetched", () => {
    installFetch(() => new Promise<Response>(() => undefined));

    renderPage();

    expect(
      screen.getByRole("progressbar", { name: "Loading family members" }),
    ).toBeInTheDocument();
  });

  it("shows an empty state when no active family members exist", async () => {
    installFetch(async () => jsonResponse([]));

    renderPage();

    expect(await screen.findByText("No family members yet")).toBeInTheDocument();
    expect(screen.getByText(/add an active family member/i)).toBeInTheDocument();
  });

  it("shows an API error and retries loading family members", async () => {
    let attempts = 0;
    installFetch(async () => {
      attempts += 1;
      return attempts === 1
        ? jsonResponse({ detail: "Family service unavailable" }, 500)
        : jsonResponse(MEMBERS);
    });

    renderPage();

    expect(await screen.findByText("Family service unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByLabelText("Child")).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("loads the selected child's ordered checklist", async () => {
    installFetch(async (input) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/2/current-assignment")) {
        return jsonResponse(
          assignment({
            family_member_id: 2,
            chore_name: "Bathroom",
            chore_description: "Clean the bathroom.",
            checklist_items: [
              { id: 21, label: "Clean sink", position: 0, is_completed: false },
              { id: 22, label: "Scrub tub", position: 1, is_completed: false },
            ],
          }),
        );
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Child"), {
      target: { value: "2" },
    });

    expect(
      await screen.findByRole("heading", { name: "Bathroom" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Clean the bathroom.")).toBeInTheDocument();
    expect(screen.getByText("0 of 2 complete today")).toBeInTheDocument();

    const checklist = screen.getByRole("list", { name: "Today's checklist" });
    expect(
      within(checklist)
        .getAllByRole("checkbox")
        .map((checkbox) => checkbox.closest("label")?.textContent),
    ).toEqual(["Clean sink", "Scrub tub"]);
  });

  it("persists a checklist toggle and reflects daily completion", async () => {
    const fetchMock = installFetch(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      if (url.endsWith("/checklist-items/11/completion") && init?.method === "PUT") {
        const isCompleted = JSON.parse(String(init.body)).is_completed as boolean;
        return jsonResponse({
          assignment_id: 10,
          completion_date: "2026-11-18",
          checklist_item: {
            id: 11,
            label: "Wipe counters",
            is_completed: isCompleted,
          },
          is_complete: false,
        });
      }
      if (url.endsWith("/checklist-items/12/completion") && init?.method === "PUT") {
        return jsonResponse({
          assignment_id: 10,
          completion_date: "2026-11-18",
          checklist_item: {
            id: 12,
            label: "Sweep floor",
            is_completed: true,
          },
          is_complete: true,
        });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Child"), {
      target: { value: "1" },
    });
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Wipe counters" }),
    );

    expect(await screen.findByText("1 of 2 complete today")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url, init]) => {
        return (
          String(url).endsWith("/checklist-items/11/completion") &&
          init?.method === "PUT" &&
          init.body ===
            JSON.stringify({
              completion_date: "2026-11-18",
              is_completed: true,
            })
        );
      }),
    ).toBe(true);

    fireEvent.click(screen.getByRole("checkbox", { name: "Sweep floor" }));

    expect(await screen.findByText("2 of 2 complete today")).toBeInTheDocument();
    expect(screen.getByText("All done for today")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Wipe counters" }));

    expect(await screen.findByText("1 of 2 complete today")).toBeInTheDocument();
    expect(screen.queryByText("All done for today")).not.toBeInTheDocument();
  });

  it("shows a no-assignment state for a child without a chore", async () => {
    installFetch(async (input) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/2/current-assignment")) {
        return jsonResponse({ detail: "No weekly assignment" }, 404);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Child"), {
      target: { value: "2" },
    });

    expect(
      await screen.findByText("No chore assigned this week"),
    ).toBeInTheDocument();
    expect(screen.getByText(/does not have a chore assigned/i)).toBeInTheDocument();
  });

  it("shows an inactive-profile state", async () => {
    installFetch(async (input) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/2/current-assignment")) {
        return jsonResponse({ detail: "Family member is inactive" }, 409);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Child"), {
      target: { value: "2" },
    });

    expect(await screen.findByText("This profile is inactive")).toBeInTheDocument();
  });

  it("keeps the checkbox unchanged when saving completion fails", async () => {
    installFetch(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      if (url.endsWith("/checklist-items/11/completion") && init?.method === "PUT") {
        return jsonResponse({ detail: "Completion service unavailable" }, 500);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Child"), {
      target: { value: "1" },
    });
    const checkbox = await screen.findByRole("checkbox", {
      name: "Wipe counters",
    });
    fireEvent.click(checkbox);

    expect(
      await screen.findByText("Completion service unavailable"),
    ).toBeInTheDocument();
    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("0 of 2 complete today")).toBeInTheDocument();
  });
});
