import { expect, test } from '@playwright/test';
import * as path from 'path';

test('full app gate: Stacks -> Duel -> Themes -> Timeline -> Book -> export', async ({ page, request }) => {
  const apiRequests: string[] = [];

  page.on('request', (req) => {
    const url = new URL(req.url());
    if (url.pathname.startsWith('/api/')) {
      apiRequests.push(`${req.method()} ${url.pathname}`);
    }
  });

  await page.goto('/');
  await expect(page.locator('h1')).toContainText('Photo Book Projects');

  const existingProjects = await page.locator('#projects-list .project-item').count();
  if (existingProjects > 0) {
    await page.locator('#projects-list .open-btn').first().click();
  } else {
    await page.locator('#project-name').fill('Gate Test Book');
    await page.locator('#create-project-btn').click();
    await page.locator('#projects-list .open-btn').first().click();
  }

  await expect(page).toHaveURL(/\/darkroom\//);
  await expect(page.locator('.brand')).toContainText('darkroom');

  await test.step('Upload fixture photos for real clustering', async () => {
    const fixtureDir = path.join(process.cwd(), 'tests', 'fixtures', 'vacation-20');
    await page.setInputFiles('#upload-input', fixtureDir);
    await expect.poll(async () => page.locator('#stacks-grid .stack-card').count()).toBeGreaterThan(0);
  });

  await test.step('Stacks: resolve one stack', async () => {
    await page.locator('.lens[data-lens="stacks"]').click();
    await expect(page.locator('#panel-stacks')).toHaveClass(/active/);

    await page.locator('#stacks-grid .stack-card').first().click();
    await expect(page.locator('#stack-modal')).toBeVisible();
    await page.locator('#sm-grid .photo-opt').first().click();
    await page.locator('#sm-confirm').click();
    await expect(page.locator('#stack-modal')).toBeHidden();
  });

  await test.step('Duel: make one duel decision', async () => {
    await page.locator('.lens[data-lens="duel"]').click();
    await expect(page.locator('#panel-duel')).toHaveClass(/active/);
    const duelCards = page.locator('#duel-wrap .duel-card');
    if ((await duelCards.count()) > 0) {
      await duelCards.first().click();
    } else {
      await expect(page.locator('#duel-wrap .duel-done')).toBeVisible();
    }
  });

  await test.step('Themes: create one extra theme', async () => {
    await page.locator('.lens[data-lens="themes"]').click();
    await expect(page.locator('#panel-themes')).toHaveClass(/active/);

    const themeCountBefore = await page.locator('#themes-canvas .theme-block').count();
    await page.locator('#panel-themes .section-header .btn-p').click();
    await expect(page.locator('#themes-canvas .theme-block')).toHaveCount(themeCountBefore + 1);
  });

  await test.step('Timeline: open timeline lens', async () => {
    await page.locator('.lens[data-lens="timeline"]').click();
    await expect(page.locator('#panel-timeline')).toHaveClass(/active/);
    await expect(page.locator('#timeline-wrap .tl-card').first()).toBeVisible();
  });

  await test.step('Book: add one page and one text block', async () => {
    await page.locator('.lens[data-lens="book"]').click();
    await expect(page.locator('#panel-book')).toHaveClass(/active/);

    await page.locator('#pages-row .add-pg').click();
    await page.locator('#panel-book .pp-txt-btn').click();
    await expect(page.locator('#page-canvas .slot.filled')).toHaveCount(1);
  });

  await test.step('Strict backend wiring assertions (expected to fail until full integration)', async () => {
    const requiredCalls = ['/intake/references', '/chapters', '/pages/'];

    for (const endpoint of requiredCalls) {
      const found = apiRequests.some((call) => call.includes(endpoint));
      expect.soft(
        found,
        `Gate failure: expected UI journey to call ${endpoint}, but no request was observed. Frontend is not wired to backend for this stage.`,
      ).toBeTruthy();
    }

    const projectId = page.url().split('/darkroom/')[1];
    const exportResponse = await request.post(`/api/projects/${projectId}/export`, {
      data: {},
    });

    expect(
      exportResponse.ok(),
      'Gate failure: /api/export is unavailable, so full-app persistence cannot be validated.',
    ).toBeTruthy();

    const exportPayload = await exportResponse.json();
    const chapters = Array.isArray(exportPayload.chapters) ? exportPayload.chapters : [];

    expect.soft(
      chapters.length,
      'Gate failure: expected /api/export to include at least one chapter after full UI journey. Got 0; persistence wiring is missing.',
    ).toBeGreaterThan(0);

    const hasPageItems = chapters.some(
      (chapter: { pages?: Array<{ items?: unknown[] }> }) =>
        Array.isArray(chapter.pages) && chapter.pages.some((p) => Array.isArray(p.items) && p.items.length > 0),
    );

    expect.soft(
      hasPageItems,
      'Gate failure: expected exported data to include page items from Book edits. None were persisted to backend.',
    ).toBeTruthy();
  });
});
