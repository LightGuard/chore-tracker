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
      await picker.locator("img").evaluateAll((images) =>
        images.every((image) => {
          const img = image as HTMLImageElement;
          return img.complete && img.naturalWidth > 0;
        }),
      ),
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
      {
        id: "quest",
        name: "Quest",
        preview_image: "/theme-previews/quest.png",
      },
      {
        id: "sticker-club-v2",
        name: "Sticker Club v2",
        preview_image: "/theme-previews/sticker-club-v2.png",
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
    const questPreview = await page.request.get("/theme-previews/quest.png");
    expect(questPreview.ok()).toBeTruthy();
    expect(questPreview.headers()["content-type"]).toContain("image/png");
    const stickerPreview = await page.request.get(
      "/theme-previews/sticker-club-v2.png",
    );
    expect(stickerPreview.ok()).toBeTruthy();
    expect(stickerPreview.headers()["content-type"]).toContain("image/png");
  });

  test("selects Quest, renders persisted progress, and updates after a checklist change", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/quest");
    const externalFontRequests: string[] = [];
    page.on("request", (request) => {
      if (/fonts\.(googleapis|gstatic)\.com/.test(request.url())) {
        externalFontRequests.push(request.url());
      }
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    const picker = page.getByRole("region", { name: "Pick a look for Alex" });
    await expect(picker).toBeVisible();
    const questOption = picker.getByRole("button", { name: /Quest/ });
    expect(
      await questOption.locator("img").evaluate((image) => {
        const img = image as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }),
    ).toBe(true);
    await questOption.click();

    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(page.locator(".quest-board")).toBeVisible();
    await expect(page.getByText("240 / 500 XP")).toBeVisible();
    await expect(page.getByText("30 XP THIS WEEK")).toBeVisible();
    await expect(page.getByText("LVL 01")).toBeVisible();
    await expect(
      page.getByText("8-DAY STREAK", { exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("Rank 2 of 4")).toHaveText("#02");
    await expect(page.getByText("10 XP TO #1")).toBeVisible();
    await expect(page.getByText("QUEST CLEAR")).toBeVisible();
    await expect(
      page.getByRole("progressbar", { name: "Progress to next level" }),
    ).toHaveAttribute("aria-valuenow", "240");

    const wipeCounters = page.getByRole("checkbox", { name: "Wipe counters" });
    await expect(wipeCounters).toBeChecked();
    await wipeCounters.click();

    await expect(page.getByText("230 / 500 XP")).toBeVisible();
    await expect(page.getByText("20 XP THIS WEEK")).toBeVisible();
    await expect(
      page.getByText("7-DAY STREAK", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("20 XP TO #1")).toBeVisible();
    await expect(page.getByText("QUEST CLEAR")).toHaveCount(0);
    await expect(wipeCounters).not.toBeChecked();

    await page.reload();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(page.locator(".quest-board")).toBeVisible();
    await expect(page.getByText("230 / 500 XP")).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: "Wipe counters" }),
    ).not.toBeChecked();

    await page.getByRole("checkbox", { name: "Wipe counters" }).click();
    await expect(page.getByText("240 / 500 XP")).toBeVisible();
    await expect(
      page.getByText("8-DAY STREAK", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("QUEST CLEAR")).toBeVisible();
    expect(externalFontRequests).toEqual([]);
  });

  test("supports keyboard objective toggles and visible Quest status text", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/quest");
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page
      .getByRole("region", { name: "Pick a look for Alex" })
      .getByRole("button", { name: /Quest/ })
      .click();
    await expect(page.locator(".quest-board")).toBeVisible();
    await expect(page.getByText("240 / 500 XP")).toBeVisible();

    const wipeCounters = page.getByRole("checkbox", { name: "Wipe counters" });
    await wipeCounters.focus();
    await expect(wipeCounters).toBeFocused();
    await page.keyboard.press("Space");

    await expect(wipeCounters).not.toBeChecked();
    await expect(page.getByText("230 / 500 XP")).toBeVisible();
    await expect(page.getByText("ACTIVE", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("progressbar", { name: "Progress to next level" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Switch child" }).click();
    await expect(
      page.getByRole("heading", { name: "Who’s playing?" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.locator(".quest-board")).toBeVisible();
  });

  test("keeps Quest usable at phone, tablet, and desktop with seven children and six objectives", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/stress");
    const themed = await page.request.put("/api/family-members/1/theme", {
      data: { theme_id: "quest" },
    });
    expect(themed.ok()).toBeTruthy();

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
      await expect(page.locator(".quest-board")).toBeVisible();
      await expect(
        page
          .getByRole("list", { name: "Today's checklist" })
          .getByRole("checkbox"),
      ).toHaveCount(6);
      await expect(
        page.getByText("CLEARED", { exact: true }).first(),
      ).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    }
  });

  test("does not inherit a child's Quest theme on admin routes", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/quest");
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page
      .getByRole("region", { name: "Pick a look for Alex" })
      .getByRole("button", { name: /Quest/ })
      .click();
    await expect(page.locator(".quest-board")).toBeVisible();

    await page.goto("/admin");
    await expect(page.locator(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
    await expect(page.getByRole("button", { name: "Theme" })).toBeDisabled();
  });

  test("selects Sticker Club v2, adds the final sticker, reloads, and removes it", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/sticker");
    const externalFontRequests: string[] = [];
    page.on("request", (request) => {
      if (/fonts\.(googleapis|gstatic)\.com/.test(request.url())) {
        externalFontRequests.push(request.url());
      }
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    const picker = page.getByRole("region", { name: "Pick a look for Alex" });
    await expect(picker).toBeVisible();
    const stickerOption = picker.getByRole("button", {
      name: /Sticker Club v2/,
    });
    expect(
      await stickerOption.locator("img").evaluate((image) => {
        const img = image as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }),
    ).toBe(true);
    await stickerOption.click();

    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(page.locator(".sticker-board")).toBeVisible();
    await expect(page.getByLabel("2 of 7 this week")).toBeVisible();
    await expect(page.locator(".sticker-board img")).toHaveCount(0);
    await expect(page.locator(".theme-sticker-club-v2 .app-brand-mark")).toBeHidden();
    await expect(page.getByText(/leaderboard|rank/i)).toHaveCount(0);

    const rail = page.getByRole("list", { name: "This week's stickers" });
    await expect(rail.getByLabel("Monday, complete")).toBeVisible();
    await expect(rail.getByLabel("Tuesday, complete")).toBeVisible();
    await expect(rail.getByLabel("Wednesday, incomplete, today")).toBeVisible();
    await expect(rail.getByLabel("Thursday, not recorded")).toBeVisible();
    await expect(rail.getByText("PART", { exact: true })).toBeVisible();
    await expect(page.getByText("STICKER 3 OF 7")).toHaveCount(0);

    const finalJob = page.getByRole("checkbox", {
      name: "Refill the soap dispenser",
    });
    await expect(finalJob).not.toBeChecked();
    await finalJob.click();
    await expect(page.getByLabel("3 of 7 this week")).toBeVisible();
    await expect(page.getByText("STICKER 3 OF 7")).toBeVisible();
    await expect(rail.getByLabel("Wednesday, complete, today")).toBeVisible();

    await page.reload();
    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(page.getByLabel("3 of 7 this week")).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: "Refill the soap dispenser" }),
    ).toBeChecked();
    await expect(page.getByText("STICKER 3 OF 7")).toBeVisible();

    const unchecked = page.getByRole("checkbox", {
      name: "Refill the soap dispenser",
    });
    await unchecked.focus();
    await expect(unchecked).toBeFocused();
    await page.keyboard.press("Space");
    await expect(page.getByLabel("2 of 7 this week")).toBeVisible();
    await expect(page.getByText("STICKER 3 OF 7")).toHaveCount(0);
    await expect(rail.getByLabel("Wednesday, incomplete, today")).toBeVisible();
    expect(externalFontRequests).toEqual([]);
  });

  test("keeps Sticker Club v2 usable when derived stats fail", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/sticker");
    await page.route("**/api/family-members/*/derived-stats", (route) =>
      route.abort(),
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page
      .getByRole("region", { name: "Pick a look for Alex" })
      .getByRole("button", { name: /Sticker Club v2/ })
      .click();

    await expect(page.getByRole("heading", { name: "Kitchen" })).toBeVisible();
    await expect(page.getByLabel("Sticker count unavailable")).toBeVisible();
    await expect(page.getByText("Sticker count unavailable")).toBeVisible();
    await expect(page.locator(".sticker-header-count")).toHaveText(
      /—\s*OF 7 STICKERS/,
    );
    await expect(page.getByRole("checkbox", { name: "Take out trash" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("clears the previous child's sticker count when switching", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/sticker");
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page
      .getByRole("region", { name: "Pick a look for Alex" })
      .getByRole("button", { name: /Sticker Club v2/ })
      .click();
    await expect(page.getByLabel("2 of 7 this week")).toBeVisible();

    await page.getByRole("button", { name: "Switch child" }).click();
    await expect(
      page.getByRole("heading", { name: "Who’s playing?" }),
    ).toBeVisible();
    await expect(page.getByText("YOU", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Sam", exact: true }).click();
    const picker = page.getByRole("region", { name: "Pick a look for Sam" });
    await expect(picker).toBeVisible();
    await expect(page.getByLabel("2 of 7 this week")).toHaveCount(0);

    await picker.getByRole("button", { name: /Sticker Club v2/ }).click();
    await expect(page.getByRole("heading", { name: "Bathroom" })).toBeVisible();
    await expect(page.getByLabel("1 of 7 this week")).toBeVisible();
  });

  test("keeps the Sticker Club v2 fixed list usable with seven children and six jobs", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/stress");
    const themed = await page.request.put("/api/family-members/1/theme", {
      data: { theme_id: "sticker-club-v2" },
    });
    expect(themed.ok()).toBeTruthy();

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
      await expect(page.locator(".sticker-board")).toBeVisible();
      const jobs = page.getByRole("list", { name: "Today's checklist" });
      await expect(jobs.getByRole("checkbox")).toHaveCount(6);
      await expect(
        page.getByRole("list", { name: "This week's stickers" }).locator("li"),
      ).toHaveCount(7);

      const listWindow = page.locator(".sticker-listwindow");
      const height = await listWindow.evaluate(
        (element) => element.getBoundingClientRect().height,
      );
      const scroll = await page.locator(".sticker-jobs").evaluate((element) => ({
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
      }));
      expect(Math.round(height)).toBe(width === 390 ? 190 : 260);
      expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);

      await page.getByRole("checkbox", { name: "Refill the soap dispenser" }).scrollIntoViewIfNeeded();
      await expect(
        page.getByRole("checkbox", { name: "Refill the soap dispenser" }),
      ).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    }
  });

  test("does not inherit a child's Sticker Club v2 theme on admin routes", async ({
    page,
    playwright,
  }) => {
    await resetFixture(playwright, "/api/__test__/scenario/sticker");
    await page.goto("/");
    await page.getByRole("button", { name: "Alex", exact: true }).click();
    await page
      .getByRole("region", { name: "Pick a look for Alex" })
      .getByRole("button", { name: /Sticker Club v2/ })
      .click();
    await expect(page.locator(".sticker-board")).toBeVisible();

    await page.goto("/admin");
    await expect(page.locator(".theme-scope")).toHaveAttribute(
      "data-theme",
      "homestead",
    );
    await expect(page.getByRole("button", { name: "Theme" })).toBeDisabled();
  });
});