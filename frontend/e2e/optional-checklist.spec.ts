import { expect, test, type Locator } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { cwd, env } from "node:process";
import { resetFixture, selectChild } from "./test-control";

const CHILD = "Riley";

async function capture(target: Locator, filename: string) {
  if (env.CAPTURE_SCREENSHOTS !== "1") return;
  const directory = resolve(cwd(), ".playwright-data/screenshots");
  mkdirSync(directory, { recursive: true });
  await target.screenshot({ path: resolve(directory, filename) });
}

test.describe.serial("optional checklist items", () => {
  test.beforeAll(async ({ playwright }) => {
    await resetFixture(playwright, "/api/__test__/scenario/optional-checklist");
  });

  test("shows optional items without requiring them for completion", async ({
    page,
  }) => {
    await page.goto("/");
    await selectChild(page, CHILD);

    const card = page.locator(".homestead-assignment-card");
    await expect(card).toBeVisible();
    await expect(card.getByText("Optional", { exact: true })).toBeVisible();
    await expect(
      card.getByText(
        "0 of 1 required complete today · 0 of 1 optional checked",
      ),
    ).toBeVisible();

    await card.getByText("Wipe counters", { exact: true }).click();
    await expect(card.getByText("All done for today")).toBeVisible();
    await expect(
      card.getByText(
        "1 of 1 required complete today · 0 of 1 optional checked",
      ),
    ).toBeVisible();
    await capture(card, "family-optional-checklist.png");

    await card.getByText(/^Sweep floor/).click();
    await expect(
      card.getByText(
        "1 of 1 required complete today · 1 of 1 optional checked",
      ),
    ).toBeVisible();
  });
});
