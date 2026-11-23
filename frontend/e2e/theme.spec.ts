import { expect, test } from "@playwright/test";
import { resetFixture } from "./test-control";

test.beforeEach(async ({ playwright }) => {
  await resetFixture(playwright);
});

test.describe.serial("theme persistence and selection flow", () => {
  test("gates the dropdown and assignment, saves Homestead, and restores after reload", async ({
    page,
  }) => {
    const externalFontRequests: string[] = [];
    page.on("request", (request) => {
      if (/fonts\.(googleapis|gstatic)\.com/.test(request.url())) {
        externalFontRequests.push(request.url());
      }
    });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { level: 1, name: "Who’s doing chores?" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Theme" })).toBeDisabled();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toHaveCount(0);

    await page.getByRole("button", { name: "Alex", exact: true }).click();
    const picker = page.getByRole("region", { name: "Pick a look for Alex" });
    await expect(picker).toBeVisible();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toHaveCount(0);
    expect(
      await picker.locator("img").evaluate((image) => {
        const img = image as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }),
    ).toBe(true);
    expect(
      await page.evaluate(() => localStorage.getItem("chore-tracker.theme.last-child")),
    ).toBeNull();

    await picker.getByRole("button", { name: /Homestead/ }).click();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Theme" })).toBeEnabled();
    expect(
      await page.locator(".theme-trigger-thumb").evaluate((image) => {
        const img = image as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }),
    ).toBe(true);
    expect(
      await page.evaluate(() => localStorage.getItem("chore-tracker.theme.last-child")),
    ).toBe("1");

    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Alex’s week" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Pick a look/ }),
    ).toHaveCount(0);
    expect(externalFontRequests).toEqual([]);
  });

  test("switches child without dropping the current child until another is chosen", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page.getByRole("button", { name: /Homestead/ }).last().click();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();

    await page.getByRole("button", { name: "Switch child" }).click();
    await expect(
      page.getByRole("heading", { name: "Choose a child" }),
    ).toBeVisible();
    await expect(page.getByText("Current", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Choose a child" }),
    ).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
  });

  test("uses Homestead for a child with no saved theme after a themed child", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page.getByRole("button", { name: /Homestead/ }).last().click();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();

    await page.getByRole("button", { name: "Switch child" }).click();
    await page.getByRole("button", { name: "Sam", exact: true }).click();
    const picker = page.getByRole("region", { name: "Pick a look for Sam" });
    await expect(picker).toBeVisible();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toHaveCount(0);
    await expect(page.locator(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
  });

  test("supports seven children and six objectives without horizontal overflow", async ({
    page,
  }) => {
    const stress = await page.request.post("/api/__test__/scenario/stress");
    expect(stress.ok()).toBeTruthy();

    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await page.evaluate(() => localStorage.clear());
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Alex", exact: true }),
      ).toBeVisible();
      expect(await page.locator(".child-option").count()).toBe(7);
      await page.getByRole("button", { name: "Alex", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
      const checklist = page.getByRole("list", { name: "Today's checklist" });
      await expect(checklist.getByRole("checkbox")).toHaveCount(6);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    }
  });

  test("loads the committed preview image from the app preview fixture", async ({
    page,
  }) => {
    const preview = await page.request.post("/api/__test__/scenario/preview");
    expect(preview.ok()).toBeTruthy();
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();

    await expect(page.locator(".theme-trigger-thumb")).toBeVisible();
    expect(
      await page.locator(".theme-trigger-thumb").evaluate((image) => {
        const img = image as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }),
    ).toBe(true);
    const catalog = await page.request.get("/api/themes");
    expect(await catalog.json()).toEqual([
      {
        id: "homestead",
        name: "Homestead",
        preview_image: "/theme-previews/homestead.png",
      },
    ]);
  });

  test("disables the theme control on unauthenticated admin routes", async ({
    page,
  }) => {
    await page.goto("/admin");
    await expect(page.getByRole("button", { name: "Theme" })).toBeDisabled();
    await expect(page.locator(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
  });

  test("opens the theme dropdown from the keyboard and closes it with Escape", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page.getByRole("button", { name: /Homestead/ }).last().click();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();

    const trigger = page.getByRole("button", { name: "Theme" });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("listbox", { name: "Available themes" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("listbox", { name: "Available themes" })).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("renders the phone assignment preview from the running app", async ({
    page,
  }) => {
    await page.goto("/");
    const preview = await page.request.get("/theme-previews/homestead.png");
    expect(preview.ok()).toBeTruthy();
    expect(preview.headers()["content-type"]).toContain("image/png");
  });
});