import { expect, test } from "@playwright/test";
import { resetFixture, selectChild, switchChild } from "./test-control";

test.beforeAll(async ({ playwright }) => {
  await resetFixture(playwright);
});

test.describe("family chore flow", () => {
  test("selects a child, loads the ordered checklist, and persists completion", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { level: 1, name: "Who’s doing chores?" }),
    ).toBeVisible();
    await expect(
      page.getByText(/choosing a name does not sign you in/i),
    ).toBeVisible();

    await selectChild(page, "Alex");

    await expect(
      page.getByRole("heading", { level: 2, name: "Kitchen" }),
    ).toBeVisible();
    await expect(page.getByText("Wipe and sweep after dinner.")).toBeVisible();

    const checklist = page.getByRole("list", { name: "Today's checklist" });
    await expect(checklist.getByRole("checkbox")).toHaveCount(3);
    expect(
      await checklist.getByRole("checkbox").evaluateAll((nodes) =>
        nodes.map((node) => node.closest("label")?.textContent?.trim()),
      ),
    ).toEqual(["Wipe counters", "Sweep floor", "Take out trash"]);

    await page.getByText("Wipe counters", { exact: true }).click();
    await expect(page.getByText("1 of 3 complete today")).toBeVisible();

    await page.getByText("Sweep floor", { exact: true }).click();
    await expect(page.getByText("2 of 3 complete today")).toBeVisible();

    await page.getByText("Take out trash", { exact: true }).click();
    await expect(page.getByText("3 of 3 complete today")).toBeVisible();
    await expect(page.getByText("All done for today")).toBeVisible();

    await page.reload();
    await selectChild(page, "Alex");

    await expect(
      page.getByRole("checkbox", { name: "Wipe counters" }),
    ).toBeChecked();
    await expect(
      page.getByRole("checkbox", { name: "Sweep floor" }),
    ).toBeChecked();
    await expect(
      page.getByRole("checkbox", { name: "Take out trash" }),
    ).toBeChecked();
    await expect(page.getByText("All done for today")).toBeVisible();

    await page.getByText("Wipe counters", { exact: true }).click();
    await expect(page.getByText("2 of 3 complete today")).toBeVisible();
    await expect(page.getByText("All done for today")).toHaveCount(0);

    await page.getByText("Wipe counters", { exact: true }).click();
    await expect(page.getByText("3 of 3 complete today")).toBeVisible();
    await expect(page.getByText("All done for today")).toBeVisible();
  });

  test("shows a clear no-assignment state", async ({ page }) => {
    await page.goto("/");
    await selectChild(page, "Riley");

    await expect(page.getByText("No chore assigned this week")).toBeVisible();
    await expect(page.getByText(/Riley does not have a chore assigned/)).toBeVisible();
  });
});


  test("renders persisted history and follows the selected child", async ({
    page,
  }) => {
    await page.goto("/");
    await selectChild(page, "Alex");
    await page.getByRole("button", { name: "View history" }).click();

    const history = page.getByRole("region", {
      name: "Completion history for Alex",
    });
    await expect(history).toBeVisible();

    const response = await page.request.get(
      "/api/family-members/1/completion-history?limit=50&offset=0",
    );
    expect(response.ok()).toBeTruthy();
    const payload = (await response.json()) as {
      items: Array<{
        week_start: string;
        chore_name: string;
        completion_date: string;
        completion_status: "complete" | "incomplete" | "not_yet_recorded";
      }>;
    };
    const statusLabels = {
      complete: "Complete",
      incomplete: "Incomplete",
      not_yet_recorded: "Not yet recorded",
    };

    for (const status of [
      "complete",
      "incomplete",
      "not_yet_recorded",
    ] as const) {
      const record = payload.items.find(
        (item) => item.completion_status === status,
      );
      expect(record).toBeTruthy();
      if (!record) throw new Error(`Missing ${status} history record`);
      const row = history.locator(
        `li:has(time[datetime="${record.completion_date}"])`,
      );
      await expect(row).toBeVisible();
      await expect(row.getByText(statusLabels[status])).toBeVisible();
    }

    const weeks = new Set(payload.items.map((item) => item.week_start));
    await expect(history.getByText(/^Week of /)).toHaveCount(weeks.size);
    for (const choreName of new Set(payload.items.map((item) => item.chore_name))) {
      await expect(
        history.getByRole("heading", { level: 3, name: choreName }),
      ).toBeVisible();
    }

    await switchChild(page, "Sam");
    const samHistory = page.getByRole("region", {
      name: "Completion history for Sam",
    });
    await expect(samHistory).toBeVisible();
    await expect(
      samHistory.getByRole("heading", { level: 3, name: "Laundry" }),
    ).toBeVisible();
    await expect(
      samHistory.getByRole("heading", { level: 3, name: "Bathroom" }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Completion history for Alex" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { level: 3, name: "Yard" }),
    ).toHaveCount(0);
  });

  test("shows empty history and replaces it when the selected child changes", async ({
    page,
  }) => {
    await page.goto("/");
    await selectChild(page, "Riley");
    await page.getByRole("button", { name: "View history" }).click();

    const emptyHistory = page.getByRole("region", {
      name: "Completion history for Riley",
    });
    await expect(emptyHistory).toBeVisible();
    await expect(
      emptyHistory.getByText("No completion history yet"),
    ).toBeVisible();

    await switchChild(page, "Sam");
    await expect(
      page.getByRole("region", { name: "Completion history for Sam" }),
    ).toBeVisible();
    await expect(emptyHistory).toHaveCount(0);
    await expect(
      page.getByText("No completion history yet"),
    ).toHaveCount(0);
  });

test.describe("phone-sized layout", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test("keeps the checklist usable and persists completion after reload", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Who’s doing chores?" })).toBeVisible();

    const horizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(horizontalOverflow).toBeLessThanOrEqual(1);

    await selectChild(page, "Sam");
    await expect(
      page.getByRole("heading", { level: 2, name: "Bathroom" }),
    ).toBeVisible();

    const checkboxLabel = page.getByText("Clean sink", { exact: true });
    const box = await checkboxLabel.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.x).toBeGreaterThanOrEqual(0);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);

    await checkboxLabel.click();
    await expect(page.getByText("1 of 2 complete today")).toBeVisible();

    await page.reload();
    await selectChild(page, "Sam");

    await expect(
      page.getByRole("checkbox", { name: "Clean sink" }),
    ).toBeChecked();
    await expect(page.getByText("1 of 2 complete today")).toBeVisible();
  });
});