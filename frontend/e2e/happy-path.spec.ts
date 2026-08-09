import { test, expect, type Page } from "@playwright/test";
import { promises as fs } from "fs";
import path from "path";
import { fileURLToPath } from "url";

// The vertical-slice E2E for M1. Drives the full happy path:
// home -> create project -> upload 8 vacation photos -> process ->
// stacks screen -> themes screen -> auto-build book -> export.
//
// Selectors use roles and accessible names per the v2 test policy.

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

async function waitForStacks(page: Page) {
  // Default filter is "Pending"; the fixture has no EXIF so every
  // stack auto-resolves. Wait for processing, then view all stacks.
  await page.getByRole("button", { name: "View All" }).click({ timeout: 30_000 });
  await expect(page.getByRole("list", { name: /stacks/i })).toBeVisible({ timeout: 30_000 });
  const items = page.getByRole("list", { name: /stacks/i }).locator("li");
  await expect(items.first()).toBeVisible({ timeout: 30_000 });
}

test("end-to-end: create project, upload, process, book, export", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /your shoeboxes/i })).toBeVisible();

  // Create a project.
  const projectName = `E2E ${Date.now()}`;
  await page.getByPlaceholder("Italy 2026").fill(projectName);
  await page.getByRole("button", { name: /^create$/i }).click();

  // We land on the project page; the top bar shows the project name.
  await expect(page.getByRole("button", { name: "Stacks", exact: true })).toBeVisible({ timeout: 10_000 });

  // Upload a handful of fixture photos.
  const files = await pickFiles(8);
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: "Add photos" }).click(),
  ]);
  await chooser.setFiles(files);

  // Wait for the upload summary to appear (matches "Added 8").
  await expect(page.getByText(/added\s+8/i)).toBeVisible({ timeout: 30_000 });

  // Stacks appear after automatic processing.
  await waitForStacks(page);

  // Visit Themes tab.
  await page.getByRole("button", { name: "Themes", exact: true }).click();
  // At least one theme exists.
  await expect(page.getByRole("button", { name: /^rename/i }).first()).toBeVisible();

  // Visit Book tab.
  await page.getByRole("button", { name: "Book", exact: true }).click();

  // Auto-build.
  await page.getByRole("button", { name: /auto-build draft/i }).click();
  // At least one slot becomes a filled image (look for img inside the pages list).
  await expect(page.locator(".slot.filled img").first()).toBeVisible({ timeout: 15_000 });

  // Export link present and points at the right URL.
  const exportLink = page.getByRole("link", { name: /export json/i });
  await expect(exportLink).toBeVisible();
  const href = await exportLink.getAttribute("href");
  expect(href).toMatch(/\/api\/projects\/.+\/export$/);
});
