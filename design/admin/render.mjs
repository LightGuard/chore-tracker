import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../../frontend/node_modules/@playwright/test/index.mjs";

const root = dirname(fileURLToPath(import.meta.url));
const baseUrl = process.env.ADMIN_MOCKUP_BASE_URL ?? "http://127.0.0.1:4174";
const themes = ["homestead", "quest", "sticker-club-v2"];
const screens = ["shell", "family", "chores", "reports", "report-detail", "invite"];
const widths = [1440, 900, 390];
const output = resolve(root, "shots");
mkdirSync(output, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
});
const errors = [];

try {
  for (const theme of themes) {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
    });
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(String(error)));

    for (const screen of screens) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto(
        baseUrl + "/admin/" + screen + ".html?theme=" + theme,
        { waitUntil: "networkidle" },
      );
      await page.waitForSelector(".admin-side");
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({
        path: resolve(output, theme + "-" + screen + ".png"),
        fullPage: true,
      });

      for (const width of widths) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(() => document.fonts.ready);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        );
        if (overflow > 1) {
          throw new Error(
            theme + " / " + screen + " overflows by " + overflow + "px at " + width + "px",
          );
        }
      }
      console.log("rendered", theme, screen);
    }
    await page.close();
  }

  const gallery = await browser.newPage({
    viewport: { width: 1700, height: 1200 },
    deviceScaleFactor: 1,
  });
  await gallery.goto(baseUrl + "/admin/index.html", { waitUntil: "networkidle" });
  await gallery.evaluate(() => document.fonts.ready);
  await gallery.screenshot({
    path: resolve(root, "overview.png"),
    fullPage: true,
  });
  await gallery.close();

  if (errors.length) {
    throw new Error("Console errors:\n" + errors.join("\n"));
  }
  console.log("wrote 18 mockup screenshots and overview.png");
} finally {
  await browser.close();
}
