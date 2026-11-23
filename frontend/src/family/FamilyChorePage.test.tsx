import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CurrentAssignment, FamilyMember } from "./api";
import { FamilyChorePage } from "./FamilyChorePage";

const THEMES = [
  {
    id: "homestead",
    name: "Homestead",
    preview_image: "/theme-previews/homestead.png",
  },
];

const MEMBERS: FamilyMember[] = [
  { id: 1, display_name: "Alex", theme_id: "homestead" },
  { id: 2, display_name: "Sam", theme_id: "homestead" },
];

const PICKER_MEMBERS: FamilyMember[] = [
  { id: 1, display_name: "Alex", theme_id: null },
  { id: 2, display_name: "Sam", theme_id: null },
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
  themes = THEMES,
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/themes")) return jsonResponse(themes);
    return handler(input, init);
  });
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

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.history.pushState({}, "", "/");
});

describe("family chore page", () => {
  it("shows a loading state while family members are fetched", () => {
    installFetch(() => new Promise<Response>(() => undefined));

    renderPage();

    expect(
      screen.getByRole("progressbar", { name: "Loading family members" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Theme" }),
    ).toBeDisabled();
  });

  it("shows an empty state when no active family members exist", async () => {
    installFetch(async () => jsonResponse([]));

    renderPage();

    expect(await screen.findByText("No family members yet")).toBeInTheDocument();
    expect(screen.getByText(/add an active family member/i)).toBeInTheDocument();
  });

  it("shows an API error and retries loading family members", async () => {
    let attempts = 0;
    installFetch(async (input) => {
      if (String(input).endsWith("/family-members/active")) {
        attempts += 1;
        return attempts === 1
          ? jsonResponse({ detail: "Family service unavailable" }, 500)
          : jsonResponse(MEMBERS);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    expect(await screen.findByText("Family service unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("button", { name: /Alex/ })).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("selects a child with a saved theme and loads the ordered checklist", async () => {
    installFetch(async (input) => {
      if (String(input).endsWith("/family-members/2/current-assignment")) {
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
      return jsonResponse(MEMBERS);
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Sam/ }));

    expect(
      await screen.findByRole("heading", { name: "Bathroom" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Pick a look/ })).toBeNull();
    expect(screen.getByText("Clean the bathroom.")).toBeInTheDocument();
    expect(screen.getByText("0 of 2 complete today")).toBeInTheDocument();

    const checklist = screen.getByRole("list", { name: "Today's checklist" });
    expect(
      within(checklist)
        .getAllByRole("checkbox")
        .map((checkbox) => checkbox.closest("label")?.textContent),
    ).toEqual(["Clean sink", "Scrub tub"]);
    expect(window.localStorage.getItem("chore-tracker.theme.last-child")).toBe("2");
  });

  it("shows the picker before assignment content and saves immediately", async () => {
    const fetchMock = installFetch(async (input, init) => {
      if (String(input).endsWith("/family-members/active")) {
        return jsonResponse(PICKER_MEMBERS);
      }
      if (
        String(input).endsWith("/family-members/1/theme") &&
        init?.method === "PUT"
      ) {
        return jsonResponse({ theme_id: "homestead" });
      }
      if (String(input).endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));

    expect(
      await screen.findByRole("heading", { name: "Pick a look for Alex" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Kitchen" }),
    ).not.toBeInTheDocument();
    expect(window.localStorage.getItem("chore-tracker.theme.last-child")).toBeNull();

    const picker = screen.getByRole("region", { name: "Pick a look for Alex" });
    fireEvent.click(within(picker).getByRole("button", { name: /Homestead/ }));

    expect(
      await screen.findByRole("heading", { name: "Kitchen" }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/family-members/1/theme") &&
          init?.method === "PUT" &&
          init.body === JSON.stringify({ theme_id: "homestead" }),
      ),
    ).toBe(true);
    expect(window.localStorage.getItem("chore-tracker.theme.last-child")).toBe("1");
    expect(
      window.localStorage.getItem("chore-tracker.theme.child.1"),
    ).toBe("homestead");
  });

  it("stays on the picker and keeps the assignment hidden when the first save fails", async () => {
    installFetch(async (input, init) => {
      if (String(input).endsWith("/family-members/active")) {
        return jsonResponse(PICKER_MEMBERS);
      }
      if (String(input).endsWith("/family-members/1/theme") && init?.method === "PUT") {
        return jsonResponse({ detail: "Theme service unavailable" }, 500);
      }
      if (String(input).endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    const picker = await screen.findByRole("region", {
      name: "Pick a look for Alex",
    });
    fireEvent.click(within(picker).getByRole("button", { name: /Homestead/ }));

    expect(
      await screen.findByText("Theme service unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Pick a look/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Kitchen" })).toBeNull();
    expect(window.localStorage.getItem("chore-tracker.theme.last-child")).toBeNull();
  });

  it("restores a remembered child with the cached theme and assignment", async () => {
    window.localStorage.setItem("chore-tracker.theme.last-child", "1");
    window.localStorage.setItem("chore-tracker.theme.child.1", "homestead");
    installFetch(async (input) => {
      if (String(input).endsWith("/family-members/active")) {
        return jsonResponse(MEMBERS);
      }
      if (String(input).endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Kitchen" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /Pick a look/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Theme" })).toBeEnabled();
  });

  it("opens Switch child, keeps the current child while open, and cancels cleanly", async () => {
    installFetch(async (input) => {
      if (String(input).endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (String(input).endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    await screen.findByRole("heading", { name: "Kitchen" });

    fireEvent.click(screen.getByRole("button", { name: "Switch child" }));
    expect(
      screen.getByRole("heading", { name: "Choose a child" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByRole("heading", { name: "Choose a child" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kitchen" })).toBeInTheDocument();
  });

  it("persists a checklist toggle and reflects daily completion", async () => {
    installFetch(async (input, init) => {
      if (String(input).endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      if (String(input).endsWith("/checklist-items/11/completion") && init?.method === "PUT") {
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
      if (String(input).endsWith("/checklist-items/12/completion") && init?.method === "PUT") {
        return jsonResponse({
          assignment_id: 10,
          completion_date: "2026-11-18",
          checklist_item: { id: 12, label: "Sweep floor", is_completed: true },
          is_complete: true,
        });
      }
      return jsonResponse(MEMBERS);
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Wipe counters" }));

    expect(await screen.findByText("1 of 2 complete today")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Sweep floor" }));
    expect(await screen.findByText("All done for today")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Wipe counters" }));
    expect(await screen.findByText("1 of 2 complete today")).toBeInTheDocument();
    expect(screen.queryByText("All done for today")).not.toBeInTheDocument();
  });

  it("shows a no-assignment state for a child without a chore", async () => {
    installFetch(async (input) => {
      if (String(input).endsWith("/family-members/2/current-assignment")) {
        return jsonResponse({ detail: "No weekly assignment" }, 404);
      }
      return jsonResponse(MEMBERS);
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Sam/ }));

    expect(
      await screen.findByText("No chore assigned this week"),
    ).toBeInTheDocument();
  });

  it("shows an inactive-profile state", async () => {
    installFetch(async (input) => {
      if (String(input).endsWith("/family-members/2/current-assignment")) {
        return jsonResponse({ detail: "Family member is inactive" }, 409);
      }
      return jsonResponse(MEMBERS);
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Sam/ }));

    expect(await screen.findByText("This profile is inactive")).toBeInTheDocument();
  });

  it("only shows history for the selected child and updates on selection", async () => {
    function historyRecord(assignmentId: number, choreName: string) {
      return {
        assignment_id: assignmentId,
        week_start: "2026-11-16",
        week_end: "2026-11-22",
        chore_name: choreName,
        chore_description: "",
        completion_date: "2026-11-20",
        completion_status: "complete",
      };
    }

    installFetch(async (input) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/1/current-assignment")) return jsonResponse(assignment());
      if (url.endsWith("/family-members/2/current-assignment")) {
        return jsonResponse(assignment({ family_member_id: 2 }));
      }
      if (url.includes("/family-members/1/completion-history")) {
        return jsonResponse({
          items: [historyRecord(10, "Kitchen")],
          total: 7,
          limit: 50,
          offset: 0,
        });
      }
      if (url.includes("/family-members/2/completion-history")) {
        return jsonResponse({
          items: [historyRecord(20, "Bathroom")],
          total: 7,
          limit: 50,
          offset: 0,
        });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    fireEvent.click(await screen.findByRole("button", { name: "View history" }));

    expect(
      await screen.findByRole("heading", { name: "Completion history for Alex" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Kitchen daily records" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Switch child" }));
    fireEvent.click(screen.getByRole("button", { name: /Sam/ }));

    expect(
      await screen.findByRole("heading", { name: "Completion history for Sam" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Bathroom daily records" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("list", { name: "Kitchen daily records" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the checkbox unchanged when saving completion fails", async () => {
    installFetch(async (input, init) => {
      if (String(input).endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      if (String(input).endsWith("/checklist-items/11/completion") && init?.method === "PUT") {
        return jsonResponse({ detail: "Completion service unavailable" }, 500);
      }
      return jsonResponse(MEMBERS);
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    const checkbox = await screen.findByRole("checkbox", { name: "Wipe counters" });
    fireEvent.click(checkbox);

    expect(
      await screen.findByText("Completion service unavailable"),
    ).toBeInTheDocument();
    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("0 of 2 complete today")).toBeInTheDocument();
  });

  it("saves a header theme change and reverts it when the save fails", async () => {
    const extraTheme = {
      id: "quest",
      name: "Quest",
      preview_image: "/theme-previews/quest.png",
    };
    let fail = true;
    installFetch(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/family-members/active")) return jsonResponse(MEMBERS);
      if (url.endsWith("/family-members/1/current-assignment")) {
        return jsonResponse(assignment());
      }
      if (url.endsWith("/family-members/1/theme") && init?.method === "PUT") {
        return fail
          ? jsonResponse({ detail: "Theme service unavailable" }, 500)
          : jsonResponse({ theme_id: "quest" });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    }, [...THEMES, extraTheme]);

    const { container } = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    await screen.findByRole("heading", { name: "Kitchen" });

    fireEvent.click(screen.getByRole("button", { name: "Theme" }));
    fireEvent.click(screen.getByRole("option", { name: /Quest/ }));

    expect(await screen.findByText("Theme service unavailable")).toBeInTheDocument();
    expect(container.querySelector(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );

    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => {
      expect(container.querySelector(".theme-scope")).toHaveAttribute(
        "data-theme",
        "quest",
      );
    });
    expect(window.localStorage.getItem("chore-tracker.theme.child.1")).toBe("quest");
  });
});