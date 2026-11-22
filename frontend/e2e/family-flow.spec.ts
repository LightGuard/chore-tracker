import { expect, test } from "@playwright/test";

test.describe("family chore flow", () => {
  test("selects a child, loads the ordered checklist, and persists completion", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { level: 1, name: "Chore Tracker" }),
    ).toBeVisible();
    await expect(
      page.getByText(/selecting a name does not sign you in/i),
    ).toBeVisible();

    await page.getByLabel("Child").selectOption({ label: "Alex" });

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
    await page.getByLabel("Child").selectOption({ label: "Alex" });

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
    await page.getByLabel("Child").selectOption({ label: "Riley" });

    await expect(page.getByText("No chore assigned this week")).toBeVisible();
    await expect(page.getByText(/Riley does not have a chore assigned/)).toBeVisible();
  });
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
    await expect(page.getByLabel("Child")).toBeVisible();

    const horizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(horizontalOverflow).toBeLessThanOrEqual(1);

    await page.getByLabel("Child").selectOption({ label: "Sam" });
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
    await page.getByLabel("Child").selectOption({ label: "Sam" });

    await expect(
      page.getByRole("checkbox", { name: "Clean sink" }),
    ).toBeChecked();
    await expect(page.getByText("1 of 2 complete today")).toBeVisible();
  });
});
