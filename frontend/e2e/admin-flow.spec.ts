import { expect, test, type Browser, type Page } from "@playwright/test";
import {
  addCredentialToNewAuthenticator,
  credentialsFor,
  enableVirtualAuthenticator,
  type WebAuthnCredential,
} from "./web-authn";

const BASE_URL = "http://localhost:5174";
const FIRST_ADMIN = "first@example.test";
const SECOND_ADMIN = "second@example.test";

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
