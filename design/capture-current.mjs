import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire(path.resolve("frontend/package.json"));
const { chromium } = require("playwright");
const executablePath = "/Users/jporter/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-arm64/chrome-headless-shell";

const assignment = {
  id: 1, family_member_id: 1, week_start: "2026-11-23", week_end: "2026-11-29",
  chore_name: "Kitchen", chore_description: "Wipe and sweep after dinner.",
  today: "2026-11-25",
  checklist_items: [
    { id: 1, label: "Wipe counters", position: 0, is_completed: true },
    { id: 2, label: "Sweep floor", position: 1, is_completed: true },
    { id: 3, label: "Take out trash", position: 2, is_completed: false },
  ],
  is_complete: false,
};

const browser = await chromium.launch({ executablePath });
for (const [name, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 2 });
  await page.route((url) => new URL(url).pathname.startsWith("/api/"), async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/family-members/active")) {
      return route.fulfill({ json: [
        { id: 1, display_name: "Alex" }, { id: 2, display_name: "Sam" },
        { id: 3, display_name: "Riley" }, { id: 4, display_name: "Avery" },
      ]});
    }
    if (url.pathname.endsWith("/family-members/1/current-assignment")) {
      return route.fulfill({ json: assignment });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
  await page.getByLabel("Child").selectOption({ label: "Alex" });
  await page.getByRole("heading", { level: 2, name: "Kitchen" }).waitFor();
  await page.waitForTimeout(300);
  await page.screenshot({ path: `design/shots/00-current-${name}.png` });
  await page.close();
}
await browser.close();
console.log("done");