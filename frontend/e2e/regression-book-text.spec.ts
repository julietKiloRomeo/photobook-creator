import { test, expect, type Page } from "@playwright/test";
import { promises as fs } from "fs";
import path from "path";
import { fileURLToPath } from "url";

// Regression for B-2 (step-2 manual finding): adding two text blocks to
// a book page must show both text blocks in order. The original bug was
// that text items beyond the 2x2 photo grid (slots 0..3) were not
// rendered at all, so the user perceived an off-by-one.

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_DIR = path.resolve(HERE, "..", "..", "tests", "fixtures", "vacation-20");

async function pickFiles(count: number): Promise<string[]> {
  const entries = await fs.readdir(FIXTURE_DIR);
  return entries
    .filter((n) => n.startsWith("vacation_") && n.endsWith(".jpg"))
    .sort()
    .slice(0, count)
    .map((n) => path.join(FIXTURE_DIR, n));
}

async function createProjectWithProcessedPhotos(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByPlaceholder("Italy 2026").fill(`Text-B2 ${Date.now()}`);
  await page.getByRole("button", { name: /^create$/i }).click();

  const files = await pickFiles(8);
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: "Add photos" }).click(),
  ]);
  await chooser.setFiles(files);
  await expect(page.getByText(/added\s+8/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "View All" })).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: "Book", exact: true }).click();
  await page.getByRole("button", { name: /auto-build draft/i }).click();
  await expect(page.locator(".slot.filled img").first()).toBeVisible({ timeout: 15_000 });
}

test("adding two text blocks in sequence shows both blocks in order", async ({ page }) => {
  await createProjectWithProcessedPhotos(page);

  // Stub window.prompt so the test is deterministic.
  await page.evaluate(() => {
    const answers = ["First note", "Second note"];
    // @ts-expect-error - test-time monkeypatch
    window.prompt = () => answers.shift() ?? null;
  });

  const firstPage = page.locator(".page").first();
  const addText = firstPage.getByRole("button", { name: /\+ text/i });

  await addText.click();
  await expect(firstPage.getByText("First note", { exact: true })).toBeVisible({
    timeout: 5_000,
  });

  await addText.click();
  await expect(firstPage.getByText("First note", { exact: true })).toBeVisible();
  await expect(firstPage.getByText("Second note", { exact: true })).toBeVisible({
    timeout: 5_000,
  });

  // Order check: First note appears before Second note in DOM order.
  const blocks = firstPage.locator("ul.text-blocks li").allTextContents();
  const texts = await blocks;
  expect(texts.join(" | ")).toMatch(/First note.*Second note/);
});
