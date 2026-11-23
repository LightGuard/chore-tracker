import { expect, test, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { cwd, env } from "node:process";
import {
  addCredentialToNewAuthenticator,
  credentialsFor,
  enableVirtualAuthenticator,
  type WebAuthnCredential,
} from "./web-authn";
import { resetFixture } from "./test-control";

const BASE_URL = "http://localhost:5174";
const FIRST_ADMIN = "first@example.test";
const SECOND_ADMIN = "second@example.test";

test.beforeAll(async ({ playwright }) => {
  await resetFixture(playwright);
});

let firstCredential: WebAuthnCredential | undefined;
let secondCredential: WebAuthnCredential | undefined;
let enrollmentUrl: string | undefined;

function requireFirstCredential(): WebAuthnCredential {
  if (!firstCredential) throw new Error("First administrator credential is missing");
  return firstCredential;
}

function requireSecondCredential(): WebAuthnCredential {
  if (!secondCredential) throw new Error("Second administrator credential is missing");
  return secondCredential;
}

async function authenticatedContext(
  browser: Browser,
  credential: WebAuthnCredential,
  email: string,
) {
  const context = await browser.newContext({ baseURL: BASE_URL });
  const page = await context.newPage();
  const authenticator = await addCredentialToNewAuthenticator(
    page,
    credential,
  );
  await signIn(page, email);

  const credentials = await credentialsFor(authenticator);
  if (email === FIRST_ADMIN) firstCredential = credentials[0];
  if (email === SECOND_ADMIN) secondCredential = credentials[0];

  return { context, page };
}

async function signIn(page: Page, email: string) {
  await page.goto("/admin");
  const signInRegion = page.getByRole("region", {
    name: "Administrator sign in",
  });
  await expect(signInRegion).toBeVisible();
  await signInRegion.getByLabel("Administrator email").fill(email);
  await signInRegion
    .getByRole("button", { name: "Sign in with passkey" })
    .click();
  await expect(
    page.getByRole("heading", { name: `Signed in as ${email}` }),
  ).toBeVisible();
}

async function captureScreenshot(page: Page, filename: string) {
  if (env.CAPTURE_SCREENSHOTS !== "1") return;
  const directory = resolve(cwd(), ".playwright-data/screenshots");
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: resolve(directory, filename),
    fullPage: true,
  });
}

function setEnrollmentTokenExpiry(expiresAt: string) {
  const frontendDirectory = cwd();
  const databasePath = resolve(
    frontendDirectory,
    ".playwright-data/chore-tracker-e2e.db",
  );
  const pythonCandidates = [
    env.PYTHON,
    resolve(frontendDirectory, "../.venv/bin/python"),
    resolve(frontendDirectory, "../.venv/Scripts/python.exe"),
    "python3",
  ];
  const python = pythonCandidates.find(
    (candidate) =>
      candidate !== undefined &&
      (candidate === "python3" || existsSync(candidate)),
  );
  if (!python) throw new Error("No Python interpreter available for test setup");

  execFileSync(
    python,
    [
      "-c",
      `import sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute(
    "UPDATE administrator_enrollment_tokens SET expires_at = ? "
    "WHERE consumed_at IS NULL",
    (sys.argv[2],),
)
connection.commit()
connection.close()
`,
      databasePath,
      expiresAt,
    ],
    { stdio: "pipe" },
  );
}

test.describe.serial("administrator passkey and management flow", () => {
  test("registers the first administrator from a clean browser context", async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL: BASE_URL });
    const page = await context.newPage();
    const authenticator = await enableVirtualAuthenticator(page);

    await page.goto("/admin");
    const setup = page.getByRole("region", {
      name: "Initial administrator setup",
    });
    await expect(setup).toBeVisible();
    await setup.getByLabel("Administrator email").fill(FIRST_ADMIN);
    await setup
      .getByRole("button", {
        name: "Create administrator and register passkey",
      })
      .click();

    await expect(
      page.getByRole("heading", { name: `Signed in as ${FIRST_ADMIN}` }),
    ).toBeVisible();
    const credentials = await credentialsFor(authenticator);
    expect(credentials).toHaveLength(1);
    firstCredential = credentials[0];

    const response = await page.request.get("/api/auth/me");
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).email).toBe(FIRST_ADMIN);

    await context.close();
  });

  test("manages family members and chores as an authenticated administrator", async ({
    browser,
  }) => {
    const { context, page } = await authenticatedContext(
      browser,
      requireFirstCredential(),
      FIRST_ADMIN,
    );

    const familyRegion = page.getByRole("region", { name: "Family members" });
    await familyRegion.getByLabel("New family member name").fill("Casey");
    await familyRegion
      .getByRole("button", { name: "Add family member" })
      .click();

    const casey = page.getByRole("article", { name: "Family member Casey" });
    await expect(casey).toBeVisible();
    await casey.getByLabel("Display name").fill("Casey Jones");
    await casey.locator("label").filter({ hasText: "Active" }).click();
    await expect(casey.getByRole("switch", { name: "Active" })).not.toBeChecked();
    await casey
      .getByRole("button", { name: "Save family member" })
      .click();

    const updatedCasey = page.getByRole("article", {
      name: "Family member Casey Jones",
    });
    await expect(updatedCasey).toBeVisible();
    await expect(updatedCasey.getByText("Inactive")).toBeVisible();

    const membersResponse = await page.request.get("/api/family-members");
    const members = await membersResponse.json();
    expect(
      members.find((member: { display_name: string }) => member.display_name === "Casey Jones")
        .is_active,
    ).toBe(false);

    const choreRegion = page.getByRole("region", { name: "Chore catalog" });
    await choreRegion.getByLabel("New chore name").fill("Garage");
    await choreRegion
      .getByLabel("New chore description")
      .fill("Park and sweep the garage.");
    await choreRegion.getByRole("button", { name: "Create chore" }).click();

    const garage = page.getByRole("article", { name: "Chore Garage" });
    await expect(garage).toBeVisible();

    await garage.getByLabel("Add checklist item").fill("Sweep garage");
    await garage.getByRole("button", { name: "Add item" }).click();
    await expect(
      garage.getByRole("listitem", { name: "Sweep garage" }),
    ).toBeVisible();

    await garage.getByLabel("Add checklist item").fill("Organize shelves");
    await garage.getByRole("button", { name: "Add item" }).click();
    await expect(
      garage.getByRole("listitem", { name: "Organize shelves" }),
    ).toBeVisible();

    await garage.getByRole("button", { name: "Activate chore" }).click();
    await expect(
      garage.getByRole("button", { name: "Deactivate chore" }),
    ).toBeVisible();

    const sweepItem = garage.getByRole("listitem", { name: "Sweep garage" });
    await sweepItem
      .getByLabel("Checklist item 1 for Garage")
      .fill("Sweep and wash garage floor");
    await sweepItem.getByRole("button", { name: "Save item" }).click();
    await expect(
      garage.getByRole("listitem", { name: "Sweep and wash garage floor" }),
    ).toBeVisible();

    const items = garage.getByRole("listitem");
    await items.nth(0).getByRole("button", { name: "Move down" }).click();
    await expect(items.nth(0)).toHaveAccessibleName("Organize shelves");
    await expect(items.nth(1)).toHaveAccessibleName(
      "Sweep and wash garage floor",
    );

    const choresResponse = await page.request.get("/api/chores");
    const chores = await choresResponse.json();
    const savedGarage = chores.find(
      (chore: { name: string }) => chore.name === "Garage",
    );
    expect(savedGarage.is_active).toBe(true);
    expect(
      savedGarage.checklist_items.map((item: { label: string }) => item.label),
    ).toEqual(["Organize shelves", "Sweep and wash garage floor"]);

    await context.close();
  });

  test("denies admin screens and APIs to an unauthenticated context", async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL: BASE_URL });
    const page = await context.newPage();

    await page.goto("/admin");

    await expect(
      page.getByRole("region", { name: "Administrator sign in" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Family members" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Chore catalog" }),
    ).toHaveCount(0);

    expect((await page.request.get("/api/chores")).status()).toBe(401);
    expect((await page.request.get("/api/family-members")).status()).toBe(401);

    await page.goto("/admin/reports");
    await expect(
      page.getByRole("region", { name: "Administrator sign in" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Report history" }),
    ).toHaveCount(0);
    expect((await page.request.get("/api/reports")).status()).toBe(401);
    expect((await page.request.get("/api/reports/2026-11-16")).status()).toBe(401);

    await page.goto("/admin/reports/2026-11-16");
    await expect(
      page.getByRole("region", { name: "Administrator sign in" }),
    ).toBeVisible();
    await expect(page.getByRole("region", { name: "Report detail" })).toHaveCount(
      0,
    );

    await context.close();
  });

  test("opens persisted report history and paginates report entries", async ({
    browser,
  }) => {
    const { context, page } = await authenticatedContext(
      browser,
      requireFirstCredential(),
      FIRST_ADMIN,
    );

    const reportsResponse = await page.request.get("/api/reports");
    expect(reportsResponse.ok()).toBeTruthy();
    const reports = (await reportsResponse.json()) as Array<{
      week_start: string;
      week_end: string;
      generated_at: string;
    }>;
    expect(reports).toHaveLength(2);
    expect(reports[0].week_start > reports[1].week_start).toBe(true);

    await page.getByRole("link", { name: "Reports" }).click();
    const history = page.getByRole("region", {
      name: "Report history",
    });
    await expect(history).toBeVisible();
    await expect(
      history.getByRole("heading", { level: 3 }).first(),
    ).toBeVisible();
    await expect(
      history.locator(`a[href="/admin/reports/${reports[0].week_start}"]`),
    ).toBeVisible();
    await captureScreenshot(page, "admin-report-history.png");

    const membersResponse = await page.request.get("/api/family-members");
    const members = (await membersResponse.json()) as Array<{
      id: number;
      display_name: string;
    }>;
    const jordan = members.find((member) => member.display_name === "Jordan");
    expect(jordan).toBeTruthy();
    if (!jordan) throw new Error("Jordan was not seeded");
    const renamed = await page.request.patch(`/api/family-members/${jordan.id}`, {
      headers: {
        Origin: BASE_URL,
        "Content-Type": "application/json",
      },
      data: { display_name: "Jordan Renamed" },
    });
    expect(renamed.ok()).toBeTruthy();

    const firstPageResponse = await page.request.get(
      `/api/reports/${reports[0].week_start}?limit=5&offset=0`,
    );
    expect(firstPageResponse.ok()).toBeTruthy();
    const firstPage = (await firstPageResponse.json()) as {
      total: number;
      entries: Array<{
        family_member_name: string;
        chore_name: string;
        completed_days: number;
        days: Array<{ date: string; status: "complete" | "incomplete" }>;
      }>;
    };
    expect(firstPage.total).toBe(6);
    expect(firstPage.entries).toHaveLength(5);

    await page
      .locator(`a[href="/admin/reports/${reports[0].week_start}"]`)
      .click();
    const detail = page.getByRole("region", { name: "Report detail" });
    await expect(detail).toBeVisible();
    await expect(
      detail.getByRole("heading", { level: 2 }),
    ).toBeVisible();
    await expect(detail.getByText("of 42 child-day slots")).toBeVisible();
    await expect(detail.getByText("Showing 1–5 of 6 entries")).toBeVisible();

    const table = detail.getByRole("table", { name: /Report entries for/ });
    for (const entry of firstPage.entries) {
      const row = table.getByRole("row", {
        name: `Report entry for ${entry.family_member_name}`,
      });
      await expect(row).toBeVisible();
      await expect(row.getByText(entry.chore_name, { exact: true })).toBeVisible();
      await expect(row.locator(".report-total-cell strong")).toHaveText(
        `${entry.completed_days} / 7`,
      );
      for (const day of entry.days) {
        const label = `${day.date}: ${
          day.status === "complete" ? "Complete" : "Incomplete"
        }`;
        await expect(row.getByLabel(label)).toBeVisible();
      }
    }
    await expect(
      table.getByRole("row", { name: "Report entry for Jordan" }),
    ).toBeVisible();
    await expect(
      table.getByRole("row", { name: "Report entry for Jordan Renamed" }),
    ).toHaveCount(0);
    await captureScreenshot(page, "admin-report-detail.png");

    await detail.getByRole("button", { name: "Next" }).click();
    await expect(detail.getByText("Showing 6–6 of 6 entries")).toBeVisible();
    const secondPageResponse = await page.request.get(
      `/api/reports/${reports[0].week_start}?limit=5&offset=5`,
    );
    const secondPage = (await secondPageResponse.json()) as {
      entries: Array<{
        family_member_name: string;
        chore_name: string;
        completed_days: number;
        days: Array<{ date: string; status: "complete" | "incomplete" }>;
      }>;
    };
    expect(secondPage.entries).toHaveLength(1);
    for (const entry of secondPage.entries) {
      const row = table.getByRole("row", {
        name: `Report entry for ${entry.family_member_name}`,
      });
      await expect(row).toBeVisible();
      await expect(row.getByText(entry.chore_name, { exact: true })).toBeVisible();
      await expect(row.locator(".report-total-cell strong")).toHaveText(
        `${entry.completed_days} / 7`,
      );
      for (const day of entry.days) {
        const label = `${day.date}: ${
          day.status === "complete" ? "Complete" : "Incomplete"
        }`;
        await expect(row.getByLabel(label)).toBeVisible();
      }
    }
    await expect(
      table.getByRole("row", { name: "Report entry for Alex" }),
    ).toHaveCount(0);

    await context.close();
  });

  test("enrolls a second administrator and authenticates both independently", async ({
    browser,
  }) => {
    const first = await authenticatedContext(
      browser,
      requireFirstCredential(),
      FIRST_ADMIN,
    );
    const secondAdminRegion = first.page.getByRole("region", {
      name: "Second administrator",
    });
    await secondAdminRegion
      .getByLabel("Administrator email")
      .fill(SECOND_ADMIN);
    await secondAdminRegion
      .getByRole("button", { name: "Create administrator invitation" })
      .click();
    await expect(
      first.page.getByText("Enrollment link created"),
    ).toBeVisible();
    enrollmentUrl = await first.page.getByLabel("Enrollment link").inputValue();
    expect(enrollmentUrl).toContain("/admin/enroll#token=");
    await first.context.close();

    setEnrollmentTokenExpiry("2000-01-01T00:00:00Z");
    const expiredContext = await browser.newContext({ baseURL: BASE_URL });
    const expiredPage = await expiredContext.newPage();
    await enableVirtualAuthenticator(expiredPage);
    await expiredPage.goto(enrollmentUrl);
    await expiredPage
      .getByRole("button", { name: "Register passkey" })
      .click();
    await expect(
      expiredPage.getByText("Enrollment token is invalid or expired"),
    ).toBeVisible();
    await expiredContext.close();

    setEnrollmentTokenExpiry("2099-01-01T00:00:00Z");
    const secondContext = await browser.newContext({ baseURL: BASE_URL });
    const secondPage = await secondContext.newPage();
    const secondAuthenticator = await enableVirtualAuthenticator(secondPage);
    await secondPage.goto(enrollmentUrl);
    const enrollment = secondPage.getByRole("region", {
      name: "Register administrator passkey",
    });
    await expect(enrollment).toBeVisible();
    await enrollment.getByRole("button", { name: "Register passkey" }).click();
    await expect(
      secondPage.getByRole("heading", {
        name: `Signed in as ${SECOND_ADMIN}`,
      }),
    ).toBeVisible();
    const credentials = await credentialsFor(secondAuthenticator);
    expect(credentials).toHaveLength(1);
    secondCredential = credentials[0];
    await secondContext.close();

    const independent = await authenticatedContext(
      browser,
      requireSecondCredential(),
      SECOND_ADMIN,
    );
    await expect(
      independent.page.getByRole("heading", {
        name: `Signed in as ${SECOND_ADMIN}`,
      }),
    ).toBeVisible();
    await independent.context.close();
  });

  test("rejects invalid and already-consumed enrollment tokens", async ({
    browser,
  }) => {
    const invalidContext = await browser.newContext({ baseURL: BASE_URL });
    const invalidPage = await invalidContext.newPage();
    await enableVirtualAuthenticator(invalidPage);
    await invalidPage.goto("/admin/enroll#token=not-a-real-token");
    await invalidPage
      .getByRole("button", { name: "Register passkey" })
      .click();
    await expect(
      invalidPage.getByText("Enrollment token is invalid or expired"),
    ).toBeVisible();
    await invalidContext.close();

    if (!enrollmentUrl) throw new Error("Enrollment URL is missing");
    const reusedContext = await browser.newContext({ baseURL: BASE_URL });
    const reusedPage = await reusedContext.newPage();
    await enableVirtualAuthenticator(reusedPage);
    await reusedPage.goto(enrollmentUrl);
    await reusedPage.getByRole("button", { name: "Register passkey" }).click();
    await expect(
      reusedPage.getByText("Enrollment token is invalid or expired"),
    ).toBeVisible();
    await reusedContext.close();
  });


  test("saves the administrator theme and reverts to Homestead on sign-out", async ({
    browser,
  }) => {
    const { context, page } = await authenticatedContext(
      browser,
      requireFirstCredential(),
      FIRST_ADMIN,
    );
    const themeButton = page.getByRole("button", { name: "Theme" });
    await expect(themeButton).toBeEnabled();

    const saved = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/auth/me/theme") &&
        response.request().method() === "PUT",
    );
    await themeButton.click();
    await page.getByRole("option", { name: /Homestead/ }).click();
    expect((await saved).status()).toBe(200);
    await expect(page.locator(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
    expect(
      await page.evaluate(() =>
        Object.keys(window.localStorage).some((key) =>
          key.startsWith("chore-tracker.theme.admin."),
        ),
      ),
    ).toBe(true);

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(
      page.getByRole("region", { name: "Administrator sign in" }),
    ).toBeVisible();
    await expect(themeButton).toBeDisabled();
    await expect(page.locator(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
    await context.close();
  });

  test("signs out, revokes access, and keeps protected screens closed after reload", async ({
    browser,
  }) => {
    const { context, page } = await authenticatedContext(
      browser,
      requireFirstCredential(),
      FIRST_ADMIN,
    );

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(
      page.getByRole("region", { name: "Administrator sign in" }),
    ).toBeVisible();
    await expect(page.getByText("You have signed out.")).toBeVisible();
    expect((await page.request.get("/api/chores")).status()).toBe(401);

    await page.reload();
    await expect(
      page.getByRole("region", { name: "Administrator sign in" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Family members" }),
    ).toHaveCount(0);

    await context.close();
  });
});