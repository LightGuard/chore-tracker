import { cleanup, render, screen } from "@testing-library/react";
import { Reshaped } from "reshaped";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminPage } from "./AdminPage";

const THEMES = [
  {
    id: "homestead",
    name: "Homestead",
    preview_image: "/theme-previews/homestead.png",
  },
  {
    id: "quest",
    name: "Quest",
    preview_image: "/theme-previews/quest.png",
  },
  {
    id: "sticker-club-v2",
    name: "Sticker Club v2",
    preview_image: "/theme-previews/sticker-club-v2.png",
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const days = Array.from({ length: 7 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 10, 16 + index));
  return {
    date: date.toISOString().slice(0, 10),
    status: "complete" as const,
  };
});

const report = {
  id: 42,
  week_start: "2026-11-16",
  week_end: "2026-11-22",
  generated_at: "2026-11-23T10:00:00Z",
  summary: {
    family_member_count: 1,
    total_days: 7,
    completed_days: 7,
    incomplete_days: 0,
  },
  entries: [
    {
      id: 1,
      family_member_name: "Alex",
      chore_name: "Kitchen",
      chore_description: "Clean the kitchen",
      completed_days: 7,
      incomplete_days: 0,
      days,
      reward: null,
    },
  ],
  total: 1,
  limit: 5,
  offset: 0,
};

function installFetch(themeId: string, path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/themes")) return jsonResponse(THEMES);
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
          theme_id: themeId,
        });
      }
      if (url.endsWith("/family-members") || url.endsWith("/chores")) {
        return jsonResponse([]);
      }
      if (url.endsWith("/reports")) return jsonResponse([]);
      if (url.includes("/reports/2026-11-16")) return jsonResponse(report);
      return jsonResponse({ detail: `Not found: ${path}` }, 404);
    }),
  );
}

function renderAdmin(path: string) {
  return render(
    <Reshaped theme="slate">
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/admin/reports/:weekStart" element={<AdminPage />} />
          <Route path="*" element={<AdminPage />} />
        </Routes>
      </MemoryRouter>
    </Reshaped>,
  );
}

it("ignores a child's cached theme for signed-in admin layouts", async () => {
  window.localStorage.setItem("chore-tracker.theme.last-child", "7");
  window.localStorage.setItem("chore-tracker.theme.child.7", "quest");
  window.localStorage.setItem("chore-tracker.theme.last-theme", "quest");
  installFetch("homestead", "/admin");
  const { container } = renderAdmin("/admin");

  await screen.findByRole("heading", {
    name: "Signed in as first@example.test",
  });

  expect(container.querySelector(".theme-scope")).toHaveAttribute(
    "data-theme",
    "homestead",
  );
  expect(container.querySelector(".admin-workspace")).toHaveAttribute(
    "data-admin-theme",
    "homestead",
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.location.hash = "";
});

describe.each(THEMES)("administrator $name layout", (theme) => {
  it("wraps the shell, family, chores, and access screens in the selected theme", async () => {
    installFetch(theme.id, "/admin");
    const { container } = renderAdmin("/admin");

    await screen.findByRole("heading", {
      name: "Signed in as first@example.test",
    });

    expect(container.querySelector(".theme-scope")).toHaveAttribute(
      "data-theme",
      theme.id,
    );
    const workspace = container.querySelector(".admin-workspace");
    expect(workspace).toHaveAttribute("data-admin-theme", theme.id);
    expect(workspace?.querySelector(".admin-side-nav")).toBeInTheDocument();
    expect(workspace?.querySelector(".admin-overview")).toBeInTheDocument();
    expect(container.querySelector("#family-members")).toBeInTheDocument();
    expect(container.querySelector("#chore-catalog")).toBeInTheDocument();
    expect(
      container.querySelector("#weekly-assignments"),
    ).toBeInTheDocument();
    expect(
      container.querySelector("#administrator-access"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Weekly assignments/ }),
    ).toHaveAttribute("href", "/admin#weekly-assignments");
  });

  it("wraps report history in the selected theme", async () => {
    installFetch(theme.id, "/admin/reports");
    const { container } = renderAdmin("/admin/reports");

    await screen.findByRole("heading", {
      name: "Signed in as first@example.test",
    });
    expect(
      await screen.findByRole("region", { name: "Report history" }),
    ).toBeInTheDocument();

    expect(container.querySelector(".admin-workspace")).toHaveAttribute(
      "data-admin-theme",
      theme.id,
    );
    expect(container.querySelector("#report-history")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("wraps report detail in the selected theme", async () => {
    installFetch(theme.id, "/admin/reports/2026-11-16");
    const { container } = renderAdmin("/admin/reports/2026-11-16");

    await screen.findByRole("heading", {
      name: "Signed in as first@example.test",
    });
    expect(
      await screen.findByRole("region", { name: "Report detail" }),
    ).toBeInTheDocument();

    expect(container.querySelector(".admin-workspace")).toHaveAttribute(
      "data-admin-theme",
      theme.id,
    );
    expect(container.querySelector("#report-detail")).toBeInTheDocument();
  });
});
