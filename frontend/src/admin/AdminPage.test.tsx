import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Reshaped } from "reshaped";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminPage } from "./AdminPage";
import { rememberAdministratorSession } from "../theme/storage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const THEMES = [
  {
    id: "homestead",
    name: "Homestead",
    preview_image: "/theme-previews/homestead.png",
  },
];

function installFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
  themes = THEMES,
) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/themes")) {
        return jsonResponse(themes);
      }
      return handler(String(input), init);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAdmin(initialEntry = "/admin") {
  return render(
    <Reshaped theme="slate">
      <MemoryRouter initialEntries={[initialEntry]}>
        <AdminPage />
      </MemoryRouter>
    </Reshaped>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.location.hash = "";
});

describe("administrator protected screens", () => {
  it("shows first-run setup and no management screens when setup is required", async () => {
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: true,
          enrollment_pending: false,
        });
      }
      return jsonResponse({ detail: "Authentication required" }, 401);
    });

    renderAdmin();

    expect(
      await screen.findByRole("heading", {
        name: "Initial administrator setup",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Family members" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Chore catalog" }),
    ).not.toBeInTheDocument();
  });

  it("keeps pre-authentication setup on Homestead even with a cached administrator theme", async () => {
    rememberAdministratorSession(1, "quest");
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: true,
          enrollment_pending: false,
        });
      }
      return jsonResponse({ detail: "Authentication required" }, 401);
    });

    const { container } = renderAdmin();

    expect(
      await screen.findByRole("heading", {
        name: "Initial administrator setup",
      }),
    ).toBeInTheDocument();
    expect(container.querySelector(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
    expect(container.querySelector(".admin-workspace")).not.toBeInTheDocument();
  });

  it("shows sign-in and no management screens for an unauthenticated visitor", async () => {
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: false,
          enrollment_pending: false,
        });
      }
      return jsonResponse({ detail: "Authentication required" }, 401);
    });

    renderAdmin();

    expect(
      await screen.findByRole("heading", { name: "Administrator sign in" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Theme" })).toBeDisabled();
    expect(
      screen.queryByRole("heading", { name: "Family members" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Chore catalog" }),
    ).not.toBeInTheDocument();
  });

  it("shows management screens to an authenticated administrator", async () => {
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: false,
          enrollment_pending: false,
        });
      }
      if (url.endsWith("/auth/me")) {
        return jsonResponse({ id: 1, email: "first@example.test" });
      }
      if (url.endsWith("/family-members") || url.endsWith("/chores")) {
        return jsonResponse([]);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderAdmin();

    expect(
      await screen.findByRole("heading", {
        name: "Signed in as first@example.test",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Family members" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Chore catalog" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Weekly assignments" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign out" }),
    ).toBeInTheDocument();
  });

  it("shows weekly report history to an authenticated administrator", async () => {
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: false,
          enrollment_pending: false,
        });
      }
      if (url.endsWith("/auth/me")) {
        return jsonResponse({ id: 1, email: "first@example.test" });
      }
      if (url.endsWith("/reports")) {
        return jsonResponse([]);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderAdmin("/admin/reports");

    await screen.findByRole("heading", {
      name: "Signed in as first@example.test",
    });
    expect(
      screen.getByRole("heading", { name: "Weekly reports" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", {
        name: "Report history",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.queryByRole("heading", { name: "Family members" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Chore catalog" }),
    ).not.toBeInTheDocument();
  });

  it("keeps weekly report history closed for an unauthenticated visitor", async () => {
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: false,
          enrollment_pending: false,
        });
      }
      return jsonResponse({ detail: "Authentication required" }, 401);
    });

    renderAdmin("/admin/reports");

    expect(
      await screen.findByRole("heading", { name: "Administrator sign in" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Report history" }),
    ).not.toBeInTheDocument();
  });

  it("returns to sign-in with a session message when a management API expires", async () => {
    installFetch((url) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: false,
          enrollment_pending: false,
        });
      }
      if (url.endsWith("/auth/me")) {
        return jsonResponse({ id: 1, email: "first@example.test" });
      }
      if (url.endsWith("/family-members")) {
        return jsonResponse({ detail: "Authentication required" }, 401);
      }
      if (url.endsWith("/chores")) return jsonResponse([]);
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderAdmin();

    expect(
      await screen.findByText("Your session expired. Sign in again."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Administrator sign in" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Family members" }),
    ).not.toBeInTheDocument();
  });

  it("saves an administrator theme, reverts on failure, and resets on sign-out", async () => {
    const quest = {
      id: "quest",
      name: "Quest",
      preview_image: "/theme-previews/quest.png",
    };
    let failTheme = true;
    installFetch(
      async (url, init) => {
        if (url.endsWith("/auth/setup")) {
          return jsonResponse({
            setup_required: false,
            enrollment_pending: false,
          });
        }
        if (url.endsWith("/auth/me")) {
          return jsonResponse({
            id: 1,
            email: "first@example.test",
            theme_id: "homestead",
          });
        }
        if (url.endsWith("/auth/me/theme") && init?.method === "PUT") {
          return failTheme
            ? jsonResponse({ detail: "Theme service unavailable" }, 500)
            : jsonResponse({ theme_id: "quest" });
        }
        if (url.endsWith("/auth/logout")) return jsonResponse({ status: "ok" });
        if (url.endsWith("/family-members") || url.endsWith("/chores")) {
          return jsonResponse([]);
        }
        return jsonResponse({ detail: "Not found" }, 404);
      },
      [...THEMES, quest],
    );

    const { container } = renderAdmin();
    expect(
      await screen.findByRole("heading", {
        name: "Signed in as first@example.test",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Theme" })).toBeEnabled();
    expect(container.querySelector(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );

    fireEvent.click(screen.getByRole("button", { name: "Theme" }));
    fireEvent.click(screen.getByRole("option", { name: /Quest/ }));
    expect(
      await screen.findByText("Theme service unavailable"),
    ).toBeInTheDocument();
    expect(container.querySelector(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );

    failTheme = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => {
      expect(container.querySelector(".theme-scope")).toHaveAttribute(
        "data-theme",
        "quest",
      );
    });
    expect(window.localStorage.getItem("chore-tracker.theme.admin.1")).toBe(
      "quest",
    );
    expect(container.querySelector(".admin-workspace")).toHaveAttribute(
      "data-admin-theme",
      "quest",
    );

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(
      await screen.findByRole("heading", { name: "Administrator sign in" }),
    ).toBeInTheDocument();
    expect(container.querySelector(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
    expect(screen.getByRole("button", { name: "Theme" })).toBeDisabled();
  });

  it("signs out and removes access to management screens", async () => {
    const fetchMock = installFetch((url, init) => {
      if (url.endsWith("/auth/setup")) {
        return jsonResponse({
          setup_required: false,
          enrollment_pending: false,
        });
      }
      if (url.endsWith("/auth/me")) {
        return jsonResponse({ id: 1, email: "first@example.test" });
      }
      if (url.endsWith("/family-members") || url.endsWith("/chores")) {
        return jsonResponse([]);
      }
      if (url.endsWith("/auth/logout") && init?.method === "POST") {
        return new Response(null, { status: 204 });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });

    renderAdmin();

    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(
      await screen.findByRole("heading", { name: "Administrator sign in" }),
    ).toBeInTheDocument();
    expect(screen.getByText("You have signed out.")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Family members" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/auth/logout") && init?.method === "POST",
      ),
    ).toBe(true);
  });
});
