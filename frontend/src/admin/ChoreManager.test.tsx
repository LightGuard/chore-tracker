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
import { ChoreManager } from "./ChoreManager";
import type { ManagedChore } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(
  handler: (
    url: string,
    init?: RequestInit,
  ) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderManager(onSessionExpired = vi.fn()) {
  render(
    <Reshaped theme="slate">
      <ChoreManager onSessionExpired={onSessionExpired} />
    </Reshaped>,
  );
  return onSessionExpired;
}

const INITIAL_CHORES: ManagedChore[] = [
  {
    id: 1,
    name: "Kitchen",
    description: "Clean the kitchen.",
    weight: 2,
    is_active: true,
    checklist_items: [
      { id: 11, label: "Sweep floor", position: 0, is_active: true, is_required: true },
      { id: 12, label: "Wipe counters", position: 1, is_active: true, is_required: true },
    ],
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("chore manager", () => {
  it("creates, edits, activates, reorders, and removes catalog entries", async () => {
    let chores: ManagedChore[] = JSON.parse(JSON.stringify(INITIAL_CHORES));
    let nextChoreId = 2;
    let nextItemId = 21;

    const fetchMock = installFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/chores") && method === "GET") {
        return jsonResponse(chores);
      }
      if (url.endsWith("/chores") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        const created: ManagedChore = {
          id: nextChoreId++,
          name: body.name,
          description: body.description,
          weight: body.weight ?? 1,
          is_active: false,
          checklist_items: [],
        };
        chores = [...chores, created];
        return jsonResponse(created, 201);
      }

      const itemMatch = url.match(/\/chores\/(\d+)\/checklist-items$/);
      if (itemMatch && method === "POST") {
        const chore = chores.find((entry) => entry.id === Number(itemMatch[1]));
        if (!chore) return jsonResponse({ detail: "Not found" }, 404);
        const body = JSON.parse(String(init?.body));
        const item = {
          id: nextItemId++,
          label: body.label,
          position: chore.checklist_items.length,
          is_active: true,
          is_required: body.is_required ?? true,
        };
        chore.checklist_items.push(item);
        return jsonResponse(item, 201);
      }

      if (url.endsWith("/checklist-order") && method === "PUT") {
        const choreId = Number(url.match(/\/chores\/(\d+)\//)?.[1]);
        const chore = chores.find((entry) => entry.id === choreId);
        const body = JSON.parse(String(init?.body));
        if (chore) {
          chore.checklist_items = body.ordered_item_ids.map(
            (id: number, position: number) => ({
              ...chore.checklist_items.find((item) => item.id === id)!,
              position,
            }),
          );
        }
        return jsonResponse(chore);
      }

      const itemIdMatch = url.match(/\/checklist-items\/(\d+)$/);
      if (itemIdMatch) {
        const itemId = Number(itemIdMatch[1]);
        for (const chore of chores) {
          const item = chore.checklist_items.find((entry) => entry.id === itemId);
          if (!item) continue;
          if (method === "DELETE") {
            chore.checklist_items = chore.checklist_items.filter(
              (entry) => entry.id !== itemId,
            );
            return new Response(null, { status: 204 });
          }
          if (method === "PATCH") {
            Object.assign(item, JSON.parse(String(init?.body)));
            return jsonResponse(item);
          }
        }
        return jsonResponse({ detail: "Not found" }, 404);
      }

      const choreIdMatch = url.match(/\/chores\/(\d+)$/);
      if (choreIdMatch && method === "PATCH") {
        const chore = chores.find(
          (entry) => entry.id === Number(choreIdMatch[1]),
        );
        if (!chore) return jsonResponse({ detail: "Not found" }, 404);
        Object.assign(chore, JSON.parse(String(init?.body)));
        return jsonResponse(chore);
      }

      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderManager();

    expect(await screen.findByRole("heading", { name: "Kitchen" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("New chore name"), {
      target: { value: "Garage" },
    });
    fireEvent.change(screen.getByLabelText("New chore description"), {
      target: { value: "Park and sweep." },
    });
    fireEvent.change(screen.getByLabelText("New chore weight (0–10)"), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create chore" }));

    const garage = await screen.findByRole("article", { name: "Chore Garage" });

    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/chores") &&
          init?.method === "POST" &&
          JSON.parse(String(init.body)).weight === 4,
      ),
    ).toBe(true);

    fireEvent.change(within(garage).getByLabelText("Add checklist item"), {
      target: { value: "Sweep garage" },
    });
    fireEvent.click(within(garage).getByRole("switch", { name: "Required" }));
    fireEvent.click(within(garage).getByRole("button", { name: "Add item" }));

    const garageItem = await screen.findByRole("listitem", {
      name: "Sweep garage",
    });
    expect(garageItem).toBeInTheDocument();
    const itemRequired = within(garageItem).getByRole("switch", {
      name: "Required",
    });
    expect(itemRequired).not.toBeChecked();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/checklist-items") &&
          init?.method === "POST" &&
          JSON.parse(String(init.body)).is_required === false,
      ),
    ).toBe(true);
    fireEvent.click(itemRequired);
    await waitFor(() =>
      expect(
        within(garageItem).getByRole("switch", { name: "Required" }),
      ).toBeChecked(),
    );

    fireEvent.click(
      within(garage).getByRole("button", { name: "Activate chore" }),
    );
    expect(
      await within(garage).findByRole("button", { name: "Deactivate chore" }),
    ).toBeInTheDocument();

    fireEvent.change(
      within(garageItem).getByLabelText("Checklist item 1 for Garage"),
      { target: { value: "Sweep garage floor" } },
    );
    fireEvent.click(
      within(garageItem).getByRole("button", { name: "Save item" }),
    );

    expect(
      await screen.findByRole("listitem", { name: "Sweep garage floor" }),
    ).toBeInTheDocument();

    const kitchen = screen.getByRole("article", { name: "Chore Kitchen" });
    expect(within(kitchen).getByLabelText("Weight (0–10)")).toHaveValue(2);
    fireEvent.change(within(kitchen).getByLabelText("Weight (0–10)"), {
      target: { value: "3" },
    });
    fireEvent.click(
      within(kitchen).getByRole("button", { name: "Save chore details" }),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).endsWith("/chores/1") &&
            init?.method === "PATCH" &&
            JSON.parse(String(init.body)).weight === 3,
        ),
      ).toBe(true),
    );
    fireEvent.click(
      within(kitchen).getAllByRole("button", { name: "Move down" })[0],
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).endsWith("/chores/1/checklist-order") &&
            init?.method === "PUT" &&
            init.body === JSON.stringify({ ordered_item_ids: [12, 11] }),
        ),
      ).toBe(true),
    );

    fireEvent.click(
      within(garage).getByRole("button", { name: "Deactivate chore" }),
    );
    await within(garage).findByRole("button", { name: "Activate chore" });
    fireEvent.click(
      within(
        screen.getByRole("listitem", { name: "Sweep garage floor" }),
      ).getByRole("button", { name: "Remove" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("listitem", { name: "Sweep garage floor" }),
      ).not.toBeInTheDocument(),
    );
  }, 15_000);

  it("shows API failures", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Chore service unavailable" }, 500),
    );

    renderManager();

    expect(
      await screen.findByText("Chore service unavailable"),
    ).toBeInTheDocument();
  });

  it("notifies the shell when the session expires", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Authentication required" }, 401),
    );
    const onSessionExpired = renderManager();

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });
  it("rejects invalid create weights before calling the API", async () => {
    const fetchMock = installFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/chores") && method === "GET") {
        return jsonResponse(INITIAL_CHORES);
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });

    renderManager();
    await screen.findByRole("heading", { name: "Kitchen" });

    fireEvent.change(screen.getByLabelText("New chore name"), {
      target: { value: "Garage" },
    });
    for (const invalid of ["11", "2.5", ""]) {
      fireEvent.change(screen.getByLabelText("New chore weight (0–10)"), {
        target: { value: invalid },
      });
      fireEvent.click(screen.getByRole("button", { name: "Create chore" }));

      expect(
        await screen.findByText(
          "Weight must be a whole number between 0 and 10.",
        ),
      ).toBeInTheDocument();
    }
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/chores") && init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("rejects invalid edit weights before calling the API", async () => {
    const fetchMock = installFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/chores") && method === "GET") {
        return jsonResponse(INITIAL_CHORES);
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });

    renderManager();
    const kitchen = await screen.findByRole("article", {
      name: "Chore Kitchen",
    });
    const weightInput = within(kitchen).getByLabelText("Weight (0–10)");
    fireEvent.change(weightInput, { target: { value: "-1" } });
    fireEvent.click(
      within(kitchen).getByRole("button", { name: "Save chore details" }),
    );

    expect(
      await screen.findByText(
        "Weight must be a whole number between 0 and 10.",
      ),
    ).toBeInTheDocument();
    expect(weightInput).toHaveValue(-1);
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/chores/1") && init?.method === "PATCH",
      ),
    ).toBe(false);
  });

  it("sends the default weight when the create field is untouched", async () => {
    let posted: unknown = null;
    let chores: ManagedChore[] = JSON.parse(JSON.stringify(INITIAL_CHORES));
    installFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/chores") && method === "GET") {
        return jsonResponse(chores);
      }
      if (url.endsWith("/chores") && method === "POST") {
        posted = JSON.parse(String(init?.body));
        const created: ManagedChore = {
          id: 2,
          name: "Garage",
          description: "",
          weight: 1,
          is_active: false,
          checklist_items: [],
        };
        chores = [...chores, created];
        return jsonResponse(created, 201);
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });

    renderManager();
    await screen.findByRole("heading", { name: "Kitchen" });
    fireEvent.change(screen.getByLabelText("New chore name"), {
      target: { value: "Garage" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create chore" }));

    await screen.findByRole("article", { name: "Chore Garage" });
    expect(posted).toEqual({
      name: "Garage",
      description: "",
      weight: 1,
    });
  });

  it("shows the API weight validation error", async () => {
    installFetch((url, init) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/chores") && method === "GET") {
        return jsonResponse(INITIAL_CHORES);
      }
      if (url.endsWith("/chores/1") && method === "PATCH") {
        return jsonResponse(
          { detail: "Weight must be a whole number between 0 and 10" },
          422,
        );
      }
      return jsonResponse({ detail: "Unexpected request" }, 500);
    });

    renderManager();
    const kitchen = await screen.findByRole("article", { name: "Chore Kitchen" });
    fireEvent.change(within(kitchen).getByLabelText("Weight (0–10)"), {
      target: { value: "5" },
    });
    fireEvent.click(
      within(kitchen).getByRole("button", { name: "Save chore details" }),
    );

    expect(
      await screen.findByText("Weight must be a whole number between 0 and 10"),
    ).toBeInTheDocument();
  });
});
