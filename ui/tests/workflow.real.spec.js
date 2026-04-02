import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const jpegFixture = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAhEAACAQQCAgMAAAAAAAAAAAABAgMABAURBhIhQVEiMf/EABUBAQEAAAAAAAAAAAAAAAAAAAID/8QAGxEAAgMAAwAAAAAAAAAAAAAAAAECBBEhMRL/2gAMAwEAAhEDEQA/ANGLQeYYqaWcQ2XMamvV2U6tswKqKPH0t5rtTUyuwksdUwxKwXHSHD9cOe6mmtF4aZzyuOCtWjlNjYQF4fujx8etkA6eNkp9TNE9Q6ZxSYQmcp7b4pG6C2mFJf/2Q==',
  'base64',
)

test('real ingest runs thumbnails and clusters', async ({ page }, testInfo) => {
  if (testInfo.project.name !== 'desktop') {
    test.skip()
  }

  const repoRoot = path.resolve(__dirname, '..', '..')
  fs.rmSync(path.join(repoRoot, '.photobook-temp'), { recursive: true, force: true })

  await page.goto('/')

  const fileInput = page.locator('input[type="file"]').first()
  await fileInput.setInputFiles([
    {
      name: '20240101T090000_a.jpg',
      mimeType: 'image/jpeg',
      buffer: jpegFixture,
    },
    {
      name: '20240101T091000_b.jpg',
      mimeType: 'image/jpeg',
      buffer: jpegFixture,
    },
  ])

  await expect(page.locator('.progress-title')).toHaveText('Building thumbnails')
  const thumbStatus = page
    .locator('.job-item')
    .filter({ hasText: 'Thumbnails' })
    .locator('.status-pill')
  await expect(thumbStatus).toHaveText('completed', { timeout: 15000 })

  const clusterStatus = page
    .locator('.job-item')
    .filter({ hasText: 'Clusters' })
    .locator('.status-pill')
  await expect(clusterStatus).toHaveText('completed', { timeout: 15000 })

  await page.locator('.stage-tabs button').filter({ hasText: 'Organize' }).click()
  await expect(page.locator('.compact-list li')).toHaveCount(1)
})
