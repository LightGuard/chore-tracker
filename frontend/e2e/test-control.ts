import type { APIRequestContext } from "@playwright/test";

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
