import { expect, test, type Page } from "@playwright/test";
import {
  E2E_NEXT_DAY,
  E2E_PRIOR_WEEK,
  E2E_TODAY,
  resetFixture,
  selectChild,
  setTestToday,
} from "./test-control";

const checks = (page: Page, labels: string[]) =>
  labels.map((label) => page.getByRole("checkbox", { name: label }));

test.describe.serial("next-day checklist and history", () => {
  test.beforeAll(async ({ playwright }) => {
    await resetFixture(playwright);
  });

  test("starts fresh tomorrow while yesterday stays complete in history", async ({
    page,
  }) => {
    await page.goto("/");
    await selectChild(page, "Alex");
    await expect(
      page.getByRole("heading", { level: 2, name: "Kitchen" }),
    ).toBeVisible();

    for (const label of ["Wipe counters", "Sweep floor", "Take out trash"]) {
      await page.getByText(label, { exact: true }).click();
    }
    await expect(page.getByText("All done for today")).toBeVisible();

    await setTestToday(page.request, E2E_NEXT_DAY);
    await page.reload();
    await selectChild(page, "Alex");

    await expect(page.getByText("0 of 3 complete today")).toBeVisible();
    for (const checkbox of checks(page, [
      "Wipe counters",
      "Sweep floor",
      "Take out trash",
    ])) {
      await expect(checkbox).not.toBeChecked();
    }

    await page.getByRole("button", { name: "View history" }).click();
    const history = page.getByRole("region", {
      name: "Completion history for Alex",
    });
    const yesterday = history.locator(
      `li:has(time[datetime="${E2E_TODAY}"])`,
    );
    await expect(yesterday).toBeVisible();
    await expect(yesterday.getByText("Complete")).toBeVisible();

    const today = history.locator(`li:has(time[datetime="${E2E_NEXT_DAY}"])`);
    await expect(today).toBeVisible();
    await expect(today.getByText("Not yet recorded")).toBeVisible();
  });
});

test.describe.serial("deterministic weekly assignment generation", () => {
  test.beforeAll(async ({ playwright }) => {
    await resetFixture(playwright, "/api/__test__/scenario/rotation");
  });

  test("assigns one deterministic chore per active child", async ({
    page,
    request,
  }) => {
    const firstResponse = await request.post("/api/__test__/rotate", {
      data: { week_start: E2E_TODAY },
    });
    expect(firstResponse.ok()).toBeTruthy();
    const first = (await firstResponse.json()) as {
      assignments: Array<{
        id: number;
        family_member_id: number;
        chore_name: string;
        checklist_items: Array<{ label: string }>;
      }>;
    };

    const secondResponse = await request.post("/api/__test__/rotate", {
      data: { week_start: E2E_TODAY },
    });
    expect(secondResponse.ok()).toBeTruthy();
    const second = (await secondResponse.json()) as typeof first;

    expect(first.assignments).toHaveLength(3);
    expect(new Set(first.assignments.map((item) => item.family_member_id)).size).toBe(
      3,
    );
    expect(second.assignments).toEqual(first.assignments);

    const membersResponse = await request.get("/api/family-members/active");
    expect(membersResponse.ok()).toBeTruthy();
    const members = (await membersResponse.json()) as Array<{
      id: number;
      display_name: string;
    }>;
    const memberIds = new Map(
      members.map((member) => [member.display_name, member.id] as const),
    );
    const byMember = new Map(
      first.assignments.map((assignment) => [
        assignment.family_member_id,
        assignment,
      ]),
    );

    for (const [name, chore] of [
      ["Alex", "Bathroom"],
      ["Riley", "Kitchen"],
      ["Sam", "Yard"],
    ] as const) {
      const memberId = memberIds.get(name);
      expect(memberId).toBeDefined();
      expect(byMember.get(memberId ?? -1)?.chore_name).toBe(chore);
    }

    const countsResponse = await request.get("/api/__test__/counts");
    expect(countsResponse.ok()).toBeTruthy();
    const counts = (await countsResponse.json()) as {
      weekly_assignments: number;
      weekly_assignment_generations: number;
    };
    expect(counts.weekly_assignments).toBe(3);
    expect(counts.weekly_assignment_generations).toBe(1);

    await page.goto("/");
    for (const [name, chore, labels] of [
      ["Alex", "Bathroom", ["Clean sink"]],
      ["Riley", "Kitchen", ["Wipe counters", "Sweep floor"]],
      ["Sam", "Yard", ["Mow lawn", "Rake leaves"]],
    ] as const) {
      await selectChild(page, name);
      await expect(
        page.getByRole("heading", { level: 2, name: chore }),
      ).toBeVisible();
      await expect(page.getByRole("checkbox")).toHaveCount(labels.length);
      for (const label of labels) {
        await expect(
          page.getByRole("checkbox", { name: label }),
        ).toBeVisible();
      }
    }
  });
});

test.describe.serial("Monday rollover", () => {
  test.beforeAll(async ({ playwright }) => {
    await resetFixture(playwright, "/api/__test__/scenario/rollover");
  });

  test("generates one report and one assignment set without duplicates", async ({
    page,
    request,
  }) => {
    const beforeResponse = await request.get("/api/__test__/counts");
    expect(beforeResponse.ok()).toBeTruthy();
    const before = (await beforeResponse.json()) as {
      weekly_assignments: number;
      weekly_reports: number;
    };
    expect(before.weekly_assignments).toBe(3);
    expect(before.weekly_reports).toBe(0);

    const firstResponse = await request.post("/api/__test__/rollover", {
      data: { now: "2026-11-09T03:00:00-07:00" },
    });
    expect(firstResponse.ok()).toBeTruthy();
    const first = (await firstResponse.json()) as {
      results: Array<{
        assignment_week_start: string;
        report_week_start: string;
        report_id: number;
        assignment_count: number;
      }>;
    };
    expect(first.results).toHaveLength(1);
    expect(first.results[0]).toMatchObject({
      assignment_week_start: E2E_TODAY,
      report_week_start: E2E_PRIOR_WEEK,
      assignment_count: 3,
    });
    expect(typeof first.results[0].report_id).toBe("number");

    const secondResponse = await request.post("/api/__test__/rollover", {
      data: { now: "2026-11-09T03:00:00-07:00" },
    });
    expect(secondResponse.ok()).toBeTruthy();
    const second = (await secondResponse.json()) as typeof first;
    expect(second.results).toEqual([]);

    const afterResponse = await request.get("/api/__test__/counts");
    expect(afterResponse.ok()).toBeTruthy();
    const after = (await afterResponse.json()) as {
      weekly_assignments: number;
      weekly_assignment_generations: number;
      weekly_reports: number;
      weekly_report_entries: number;
      weekly_report_days: number;
      weekly_rollover_state: number;
    };
    expect(after).toMatchObject({
      weekly_assignments: 6,
      weekly_assignment_generations: 2,
      weekly_reports: 1,
      weekly_report_entries: 3,
      weekly_report_days: 21,
      weekly_rollover_state: 1,
    });

    const reportResponse = await request.get(
      `/api/__test__/report/${E2E_PRIOR_WEEK}`,
    );
    expect(reportResponse.ok()).toBeTruthy();
    const report = (await reportResponse.json()) as {
      summary: {
        family_member_count: number;
        total_days: number;
        completed_days: number;
        incomplete_days: number;
      };
      entries: Array<{
        family_member_name: string;
        chore_name: string;
        completed_days: number;
        incomplete_days: number;
      }>;
    };
    expect(report.summary).toEqual({
      family_member_count: 3,
      total_days: 21,
      completed_days: 10,
      incomplete_days: 11,
    });
    expect(report.entries).toHaveLength(3);
    for (const [name, chore, completed, incomplete] of [
      ["Alex", "Bathroom", 7, 0],
      ["Riley", "Kitchen", 3, 4],
      ["Sam", "Yard", 0, 7],
    ] as const) {
      expect(report.entries).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            family_member_name: name,
            chore_name: chore,
            completed_days: completed,
            incomplete_days: incomplete,
          }),
        ]),
      );
    }

    await page.goto("/");
    for (const [name, chore] of [
      ["Alex", "Kitchen"],
      ["Riley", "Yard"],
      ["Sam", "Bathroom"],
    ] as const) {
      await selectChild(page, name);
      await expect(
        page.getByRole("heading", { level: 2, name: chore }),
      ).toBeVisible();
    }
  });
});