import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const baseUrl = process.env.PREVIEW_BASE_URL ?? "http://localhost:5174";
const output = resolve(
  process.cwd(),
  "public/theme-previews/homestead.png",
);

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
});
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});

try {
  const reset = await page.request.post(
    `${baseUrl}/api/__test__/scenario/preview`,
  );
  if (!reset.ok()) {
    throw new Error(
      `Preview fixture failed: ${reset.status()} ${await reset.text()}`,
    );
  }

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Alex", exact: true }).click();
  await page.getByRole("heading", { name: "Kitchen" }).waitFor();
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