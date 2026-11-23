import { expect, type APIRequestContext, type Page } from "@playwright/test";

const BASE_URL = "http://localhost:5174";

type PlaywrightApi = {
  request: {
    newContext(options: { baseURL: string }): Promise<APIRequestContext>;
  };
};

export const E2E_TODAY = "2026-11-09";
export const E2E_NEXT_DAY = "2026-11-10";
export const E2E_PRIOR_WEEK = "2026-11-02";

export async function resetFixture(
  playwright: PlaywrightApi,
  path = "/api/__test__/reset",
): Promise<void> {
  const request = await playwright.request.newContext({ baseURL: BASE_URL });
  try {
    const response = await request.post(path);
    if (!response.ok()) {
      throw new Error(
        `Fixture reset failed: ${response.status()} ${await response.text()}`,
      );
    }
  } finally {
    await request.dispose();
  }
}

export async function setTestToday(
  request: APIRequestContext,
  day: string,
): Promise<void> {
  const response = await request.post("/api/__test__/today", {
    data: { date: day },
  });
  if (!response.ok()) {
    throw new Error(
      `Setting the test date failed: ${response.status()} ${await response.text()}`,
    );
  }
}

/**
 * Select a child, saving Homestead first when the child has no theme yet.
 * Repeated calls after a reload are harmless when the child is already active.
 */
export async function selectChild(page: Page, name: string): Promise<void> {
  let child = page.getByRole("button", { name, exact: true });
  if ((await child.count()) === 0) {
    const switchButton = page.getByRole("button", { name: "Switch child" });
    if ((await switchButton.count()) === 0) return;
    await switchButton.click();
    child = page.getByRole("button", { name, exact: true });
  }
  await child.click();

  const picker = page.getByRole("region", { name: /Pick a look for/ });
  if (await picker.isVisible().catch(() => false)) {
    await picker.getByRole("button", { name: /Homestead/ }).click();
    await expect(picker).toBeHidden();
  }
}

export async function switchChild(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name: "Switch child" }).click();
  await selectChild(page, name);
}