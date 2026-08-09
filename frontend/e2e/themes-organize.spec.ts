import { test, expect, type Page } from "@playwright/test";
import { promises as fs } from "fs";
import path from "path";
import { fileURLToPath } from "url";

// Covers the curation controls on the Themes screen:
// drag a stack into another theme, and delete a theme.
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

async function createProjectWithPhotos(page: Page, count: number) {
  await page.goto("/");
  await page.getByPlaceholder("Italy 2026").fill(`Themes ${Date.now()}`);
  await page.getByRole("button", { name: /^create$/i }).click();
  await expect(page.getByRole("button", { name: "Stacks", exact: true })).toBeVisible({
    timeout: 10_000,
  });

  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: "Add photos" }).click(),
  ]);
  await chooser.setFiles(await pickFiles(count));
  await expect(page.getByText(new RegExp(`added\\s+${count}`, "i"))).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "Themes", exact: true }).click();
}

/** The card for a theme, located by its heading. */
function themeCard(page: Page, name: string) {
  return page.locator("article").filter({ has: page.getByRole("heading", { name, exact: true }) });
}

test("drags a stack into another theme and back out to Unassigned", async ({
  page,
  isMobile,
}) => {
  // Touch devices do not implement HTML5 drag-and-drop at all; the
  // tap-to-move path below is the supported route there.
  test.skip(!!isMobile, "HTML5 drag-and-drop is pointer-only");
  await createProjectWithPhotos(page, 4);

  await page.getByPlaceholder(/new theme name/i).fill("Keepers");
  await page.getByRole("button", { name: /^add theme$/i }).click();

  const keepers = themeCard(page, "Keepers");
  const unassigned = themeCard(page, "Unassigned");
  await expect(keepers).toBeVisible();
  await expect(keepers.getByText("No stacks in this theme.")).toBeVisible();

  // The auto-proposed theme holds every stack; move one into Keepers.
  const auto = page
    .locator("article")
    .filter({ has: page.getByRole("button", { name: /^rename undated photos$/i }) });
  await expect(auto.getByRole("button", { name: /stack with \d+ photos/i })).toHaveCount(4);

  await auto.getByRole("button", { name: /stack with \d+ photos/i }).first().dragTo(keepers);

  await expect(keepers.getByRole("button", { name: /stack with \d+ photos/i })).toHaveCount(1);
  await expect(auto.getByRole("button", { name: /stack with \d+ photos/i })).toHaveCount(3);

  // Drag it out of the theme entirely.
  await keepers.getByRole("button", { name: /stack with \d+ photos/i }).dragTo(unassigned);

  await expect(keepers.getByText("No stacks in this theme.")).toBeVisible();
  await expect(
    unassigned.getByRole("button", { name: /unassigned stack with \d+ photos/i }),
  ).toHaveCount(1);
});

test("deletes a theme and returns its stacks to Unassigned", async ({ page }) => {
  await createProjectWithPhotos(page, 4);

  const auto = themeCard(page, "Undated photos");
  await expect(auto.getByRole("button", { name: /stack with \d+ photos/i })).toHaveCount(4);

  page.once("dialog", (dialog) => dialog.accept());
  await auto.getByRole("button", { name: /^delete undated photos$/i }).click();

  await expect(page.getByRole("heading", { name: "Undated photos" })).toHaveCount(0);
  await expect(
    themeCard(page, "Unassigned").getByRole("button", { name: /unassigned stack with \d+ photos/i }),
  ).toHaveCount(4);
});

test("taps a stack and moves it to another theme", async ({ page }) => {
  await createProjectWithPhotos(page, 4);

  await page.getByPlaceholder(/new theme name/i).fill("Keepers");
  await page.getByRole("button", { name: /^add theme$/i }).click();

  const keepers = themeCard(page, "Keepers");
  const auto = themeCard(page, "Undated photos");

  await auto.getByRole("button", { name: /stack with \d+ photos/i }).first().click();
  await expect(page.getByText(/tap a theme below to move/i)).toBeVisible();
  await keepers.getByRole("button", { name: /move selected stack here/i }).click();

  await expect(keepers.getByRole("button", { name: /stack with \d+ photos/i })).toHaveCount(1);
  await expect(auto.getByRole("button", { name: /stack with \d+ photos/i })).toHaveCount(3);
});
