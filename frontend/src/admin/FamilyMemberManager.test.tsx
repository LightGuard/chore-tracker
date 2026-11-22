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
import { FamilyMemberManager } from "./FamilyMemberManager";
import type { FamilyMember } from "./api";

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
      <FamilyMemberManager onSessionExpired={onSessionExpired} />
    </Reshaped>,
  );
  return onSessionExpired;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("family member manager", () => {
  it("lists, creates, and edits family members", async () => {
    const members: FamilyMember[] = [
      { id: 1, display_name: "Alex", is_active: true },
    ];
    const fetchMock = installFetch((url, init) => {
      if (url.endsWith("/family-members") && (!init || !init.method)) {
        return jsonResponse(members);
      }
      if (url.endsWith("/family-members") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        const created = {
          id: 2,
          display_name: body.display_name,
          is_active: body.is_active,
        };
        members.push(created);
        return jsonResponse(created, 201);
      }
      if (url.endsWith("/family-members/1") && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        Object.assign(members[0], body);
        return jsonResponse(members[0]);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderManager();

    expect(await screen.findByText("Alex")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("New family member name"), {
      target: { value: "Casey" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add family member" }));

    expect(await screen.findByText("Casey")).toBeInTheDocument();

    const alexRow = screen.getByRole("article", {
      name: "Family member Alex",
    });
    fireEvent.change(within(alexRow).getByLabelText("Display name"), {
      target: { value: "Alexandra" },
    });
    fireEvent.click(within(alexRow).getByRole("switch", { name: "Active" }));
    fireEvent.click(
      within(alexRow).getByRole("button", { name: "Save family member" }),
    );

    expect(
      await screen.findByRole("article", { name: "Family member Alexandra" }),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("article", { name: "Family member Alexandra" }),
      ).getByText("Inactive"),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url, init]) => {
        return (
          String(url).endsWith("/family-members/1") &&
          init?.method === "PATCH" &&
          init.body ===
            JSON.stringify({ display_name: "Alexandra", is_active: false })
        );
      }),
    ).toBe(true);
  });

  it("rejects a blank display name before calling the API", async () => {
    const fetchMock = installFetch((url) => {
      if (url.endsWith("/family-members")) return jsonResponse([]);
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderManager();

    await screen.findByText("No family members yet");
    fireEvent.change(screen.getByLabelText("New family member name"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add family member" }));

    expect(
      await screen.findByText("Display name must not be blank."),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);
  });

  it("shows API failures", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Family service unavailable" }, 500),
    );

    renderManager();

    expect(
      await screen.findByText("Family service unavailable"),
    ).toBeInTheDocument();
  });

  it("notifies the shell when the session expires", async () => {
    installFetch(() =>
      jsonResponse({ detail: "Authentication required" }, 401),
    );
    const onSessionExpired = renderManager();

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });
});
