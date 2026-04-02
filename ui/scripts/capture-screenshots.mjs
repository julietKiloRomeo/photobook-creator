import { chromium } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..', '..')
const outputDir = path.resolve(repoRoot, 'docs', 'images', 'ui')
const baseURL = process.env.UI_BASE_URL || 'http://127.0.0.1:4173'

async function captureStage(page, label, filename) {
  await page.getByRole('button', { name: label }).click()
  await page.getByRole('heading', { name: label }).waitFor()
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(outputDir, filename), fullPage: true })
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true })
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.goto(baseURL, { waitUntil: 'networkidle' })

  await page.getByRole('heading', { name: /Project:/ }).waitFor()
  await page.screenshot({ path: path.join(outputDir, 'intake.png'), fullPage: true })

  await captureStage(page, 'Clean', 'clean.png')
  await captureStage(page, 'Build', 'build.png')

  await browser.close()
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
