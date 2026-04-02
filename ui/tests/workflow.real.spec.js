import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const jpegFixture = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAhEAACAQQCAgMAAAAAAAAAAAABAgMABAURBhIhQVEiMf/EABUBAQEAAAAAAAAAAAAAAAAAAAID/8QAGxEAAgMAAwAAAAAAAAAAAAAAAAECBBEhMRL/2gAMAwEAAhEDEQA/ANGLQeYYqaWcQ2XMamvV2U6tswKqKPH0t5rtTUyuwksdUwxKwXHSHD9cOe6mmtF4aZzyuOCtWjlNjYQF4fujx8etkA6eNkp9TNE9Q6ZxSYQmcp7b4pG6C2mFJf/2Q==',
  'base64',
)

test('real ingest runs thumbnails and clusters', async ({ page }, testInfo) => {
  if (testInfo.project.name !== 'desktop') {
    test.skip()
  }
  if (!process.env.REAL_BACKEND) {
    test.skip()
  }

  const currentDir = path.dirname(fileURLToPath(import.meta.url))
  const repoRoot = path.resolve(currentDir, '..', '..')
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

  await expect(page.getByText('Building thumbnails')).toBeVisible()
  await expect(page.getByText('Clusters')).toBeVisible({ timeout: 15000 })
})
