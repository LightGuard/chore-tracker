import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(path.resolve("frontend/package.json"));
const { chromium } = require("playwright");

const executablePath =
  "/Users/jporter/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-arm64/chrome-headless-shell";

const jobs = [
  { id: "01-homestead", file: "homestead/phone.html", out: "01-homestead-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "01-homestead", file: "homestead/phone-done.html", out: "01-homestead-phone-done.png", w: 390, h: 844, dsf: 3 },
  { id: "01-homestead", file: "homestead/desktop.html", out: "01-homestead-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "02-sticker-club", file: "sticker-club/phone.html", out: "02-sticker-club-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "02-sticker-club", file: "sticker-club/phone-done.html", out: "02-sticker-club-phone-done.png", w: 390, h: 844, dsf: 3 },
  { id: "02-sticker-club", file: "sticker-club/desktop.html", out: "02-sticker-club-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "03-still", file: "still/phone.html", out: "03-still-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "03-still", file: "still/phone-done.html", out: "03-still-phone-done.png", w: 390, h: 844, dsf: 3 },
  { id: "03-still", file: "still/desktop.html", out: "03-still-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "04-quest", file: "quest/phone.html", out: "04-quest-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "04-quest", file: "quest/phone-select.html", out: "04-quest-phone-select.png", w: 390, h: 844, dsf: 3 },
  { id: "04-quest", file: "quest/desktop.html", out: "04-quest-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "05-ledger", file: "ledger/phone.html", out: "05-ledger-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "05-ledger", file: "ledger/phone-archive.html", out: "05-ledger-phone-archive.png", w: 390, h: 844, dsf: 3 },
  { id: "05-ledger", file: "ledger/desktop.html", out: "05-ledger-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "06-matchday", file: "matchday/phone.html", out: "06-matchday-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "06-matchday", file: "matchday/phone-fulltime.html", out: "06-matchday-phone-fulltime.png", w: 390, h: 844, dsf: 3 },
  { id: "06-matchday", file: "matchday/desktop.html", out: "06-matchday-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "07-checkpoint", file: "checkpoint/phone.html", out: "07-checkpoint-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "07-checkpoint", file: "checkpoint/phone-week.html", out: "07-checkpoint-phone-week.png", w: 390, h: 844, dsf: 3 },
  { id: "07-checkpoint", file: "checkpoint/desktop.html", out: "07-checkpoint-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "08-wayfinder", file: "wayfinder/phone.html", out: "08-wayfinder-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "08-wayfinder", file: "wayfinder/phone-complete.html", out: "08-wayfinder-phone-complete.png", w: 390, h: 844, dsf: 3 },
  { id: "08-wayfinder", file: "wayfinder/desktop.html", out: "08-wayfinder-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "09-homescreen", file: "homescreen/phone.html", out: "09-homescreen-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "09-homescreen", file: "homescreen/phone-achievements.html", out: "09-homescreen-phone-achievements.png", w: 390, h: 844, dsf: 3 },
  { id: "09-homescreen", file: "homescreen/desktop.html", out: "09-homescreen-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "10-sticker-club-v2", file: "sticker-club/v2/phone.html", out: "10-sticker-club-v2-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "10-sticker-club-v2", file: "sticker-club/v2/phone-scroll.html", out: "10-sticker-club-v2-phone-scroll.png", w: 390, h: 844, dsf: 3 },
  { id: "10-sticker-club-v2", file: "sticker-club/v2/phone-done.html", out: "10-sticker-club-v2-phone-done.png", w: 390, h: 844, dsf: 3 },
  { id: "10-sticker-club-v2", file: "sticker-club/v2/desktop.html", out: "10-sticker-club-v2-desktop.png", w: 1440, h: 900, dsf: 2 },
  { id: "11-quest-light", file: "quest/light/phone.html", out: "11-quest-light-phone.png", w: 390, h: 844, dsf: 3 },
  { id: "11-quest-light", file: "quest/light/phone-scroll.html", out: "11-quest-light-phone-scroll.png", w: 390, h: 844, dsf: 3 },
  { id: "11-quest-light", file: "quest/light/phone-done.html", out: "11-quest-light-phone-done.png", w: 390, h: 844, dsf: 3 },
  { id: "11-quest-light", file: "quest/light/desktop.html", out: "11-quest-light-desktop.png", w: 1440, h: 900, dsf: 2 },
];

const filter = process.argv[2];
const selected = filter ? jobs.filter((j) => j.id.includes(filter) || j.file.includes(filter)) : jobs;
const browser = await chromium.launch({ executablePath });
for (const job of selected) {
  const page = await browser.newPage({
    viewport: { width: job.w, height: job.h },
    deviceScaleFactor: job.dsf,
  });
  await page.goto(pathToFileURL(path.resolve("design/concepts", job.file)).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important}" });
  await page.waitForTimeout(120);
  await page.screenshot({ path: path.resolve("design/shots", job.out) });
  console.log("rendered", job.out);
  await page.close();
}
await browser.close();