import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(path.resolve("frontend/package.json"));
const { chromium } = require("playwright");
const executablePath = "/Users/jporter/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-arm64/chrome-headless-shell";
const jobs = [
  { file: "overview.html", out: "00-overview.png", w: 1800, h: 1600 },
  { file: "01-homestead.html", out: "01-homestead-board.png", w: 1800, h: 1170 },
  { file: "02-sticker-club.html", out: "02-sticker-club-board.png", w: 1800, h: 1170 },
  { file: "03-still.html", out: "03-still-board.png", w: 1800, h: 1170 },
  { file: "04-quest.html", out: "04-quest-board.png", w: 1800, h: 1170 },
  { file: "05-ledger.html", out: "05-ledger-board.png", w: 1800, h: 1170 },
  { file: "06-matchday.html", out: "06-matchday-board.png", w: 1800, h: 1170 },
  { file: "07-checkpoint.html", out: "07-checkpoint-board.png", w: 1800, h: 1170 },
  { file: "08-wayfinder.html", out: "08-wayfinder-board.png", w: 1800, h: 1170 },
  { file: "09-homescreen.html", out: "09-homescreen-board.png", w: 1800, h: 1170 },
  { file: "10-sticker-club-v2.html", out: "10-sticker-club-v2-board.png", w: 1800, h: 1170 },
  { file: "11-quest-light.html", out: "11-quest-light-board.png", w: 1800, h: 1170 },
];
const browser = await chromium.launch({ executablePath });
for (const job of jobs) {
  const page = await browser.newPage({ viewport: { width: job.w, height: job.h }, deviceScaleFactor: 1.5 });
  await page.goto(pathToFileURL(path.resolve("design/boards", job.file)).href, { waitUntil: "load" });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map((img) => img.decode().catch(() => {})));
  });
  await page.waitForTimeout(150);
  await page.screenshot({ path: path.resolve("design/boards", job.out) });
  console.log("rendered", job.out);
  await page.close();
}
await browser.close();