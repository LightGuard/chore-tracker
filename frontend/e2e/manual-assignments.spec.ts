import { expect, test, type Locator } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { cwd, env } from "node:process";
import { resetFixture } from "./test-control";
import { enableVirtualAuthenticator } from "./web-authn";

const BASE_URL = "http://localhost:5174";
const ADMIN = "first@example.test";
const TARGET_WEEK = "2026-11-09";

async function capturePanel(panel: Locator, filename: string) {
  if (env.CAPTURE_SCREENSHOTS !== "1") return;
  const directory = resolve(cwd(), ".playwright-data/screenshots");
  mkdirSync(directory, { recursive: true });
  await panel.screenshot({
    path: resolve(directory, filename),
  });
}

test.describe.serial("manual weekly assignment generation", () => {
  test.beforeAll(async ({ playwright }) => {
    await resetFixture(playwright, "/api/__test__/scenario/rotation");
  });

  test("generates a selected week and reports an existing week", async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL: BASE_URL });
    const page = await context.newPage();
    await enableVirtualAuthenticator(page);

    await page.goto("/admin");
    const setup = page.getByRole("region", {
      name: "Initial administrator setup",
    });
    await expect(setup).toBeVisible();
    await setup.getByLabel("Administrator email").fill(ADMIN);
    await setup
      .getByRole("button", {
        name: "Create administrator and register passkey",
      })
      .click();
    await expect(
      page.getByRole("heading", { name: `Signed in as ${ADMIN}` }),
    ).toBeVisible();

    await page.goto("/admin#weekly-assignments");
    const panel = page.getByRole("region", { name: "Weekly assignments" });
    await expect(panel).toBeVisible();
    await page.addStyleTag({
      content: ".app-header { display: none !important; }",
    });
    await panel.getByLabel("Target week").fill(TARGET_WEEK);
    await panel.getByRole("button", { name: "Generate assignments" }).click();

    await expect(
      panel.getByText("Assignments generated", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByText(
        "Generated 3 assignments for Nov 9 – 15, 2026.",
      ),
    ).toBeVisible();
    await expect(panel.getByText("Alex", { exact: true })).toBeVisible();
    await expect(panel.getByText("Bathroom", { exact: true })).toBeVisible();
    await expect(panel.getByText("Riley", { exact: true })).toBeVisible();
    await expect(panel.getByText("Kitchen", { exact: true })).toBeVisible();
    await capturePanel(panel, "manual-assignments-generated.png");
    if (env.CAPTURE_SCREENSHOTS === "1") {
      await panel.scrollIntoViewIfNeeded();
      await page.screenshot({
        path: resolve(
          cwd(),
          ".playwright-data/screenshots/manual-assignments-page.png",
        ),
      });
    }

    await panel.getByRole("button", { name: "Generate assignments" }).click();
    await expect(
      panel.getByText("Assignments already exist", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByText(/Nothing changed; 3 assignments already existed/),
    ).toBeVisible();
    await capturePanel(panel, "manual-assignments-existing.png");

    await context.close();
  });
});
