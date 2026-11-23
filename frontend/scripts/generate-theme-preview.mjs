import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const baseUrl = process.env.PREVIEW_BASE_URL ?? "http://localhost:5174";
const themeId = process.env.PREVIEW_THEME ?? "homestead";
const scenario =
  themeId === "quest"
    ? "quest-preview"
    : themeId === "sticker-club-v2"
      ? "sticker-preview"
      : "preview";
const output = resolve(process.cwd(), `public/theme-previews/${themeId}.png`);

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
});
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});

try {
  const reset = await page.request.post(
    `${baseUrl}/api/__test__/scenario/${scenario}`,
  );
  if (!reset.ok()) {
    throw new Error(
      `Preview fixture failed: ${reset.status()} ${await reset.text()}`,
    );
  }

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Alex", exact: true }).click();
  await page.getByRole("heading", { name: "Kitchen" }).waitFor();
  if (themeId === "quest") {
    await page.locator(".quest-xp").filter({ hasText: "XP" }).waitFor();
  }
  if (themeId === "sticker-club-v2") {
    await page
      .locator(".sticker-header-count b")
      .filter({ hasText: /\d/ })
      .waitFor();
  }
  await page.addStyleTag({
    content: ".theme-trigger-thumb{visibility:hidden}",
  });
  await page.waitForTimeout(250);

  mkdirSync(resolve(process.cwd(), "public/theme-previews"), {
    recursive: true,
  });
  await page.screenshot({ path: output });
  console.log(`wrote ${output} from ${baseUrl}`);
} finally {
  await browser.close();
}
