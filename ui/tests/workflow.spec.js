import { expect, test } from '@playwright/test'

const states = ['empty', 'running', 'completed', 'error']

const thumbnailsPayload = {
  items: [
    {
      photo_path: '/tmp/20240101T090000_a.jpg',
      size: 256,
      path: '/tmp/cache/a_256.jpg',
      width: 256,
      height: 180,
    },
    {
      photo_path: '/tmp/20240101T091000_b.jpg',
      size: 256,
      path: '/tmp/cache/b_256.jpg',
      width: 256,
      height: 180,
    },
  ],
}

const clusterPayload = {
  items: [
    {
      id: 1,
      name: 'Event 1',
      start_at: '2024-01-01T09:00:00',
      end_at: '2024-01-01T09:10:00',
      kind: 'event',
      photos: [
        { photo_path: '/tmp/20240101T090000_a.jpg', rank: 1, role: 'member' },
        { photo_path: '/tmp/20240101T091000_b.jpg', rank: 2, role: 'member' },
      ],
    },
    {
      id: 2,
      name: 'Event 2',
      start_at: '2024-01-01T14:00:00',
      end_at: '2024-01-01T14:10:00',
      kind: 'event',
      photos: [{ photo_path: '/tmp/20240101T140000_c.jpg', rank: 1, role: 'member' }],
    },
  ],
}

const duplicatePayload = {
  items: [
    {
      id: 1,
      photos: [
        {
          photo_path: '/tmp/20240101T141500_dup.jpg',
          distance: 0,
          is_best: 1,
        },
        {
          photo_path: '/tmp/20240101T142000_dup.jpg',
          distance: 0,
          is_best: 0,
        },
      ],
    },
  ],
}

function setupRoutes(page, state) {
  let jobPolls = 0
  page.on('request', (request) => {
    if (request.url().includes('/api/ingest')) {
      jobPolls = 0
    }
  })

  return page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/ingest') {
      if (state === 'error') {
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'ingest failed' }),
        })
      }
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          files: ['/tmp/20240101T090000_a.jpg', '/tmp/20240101T091000_b.jpg'],
          job_id: 'job-thumbs',
          cluster_job_id: 'job-clusters',
        }),
      })
    }

    if (url.pathname.startsWith('/api/jobs/')) {
      jobPolls += 1
      if (state === 'error') {
        return route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'job-thumbs',
            kind: 'thumbnails',
            status: 'failed',
            total: 4,
            completed: 1,
          }),
        })
      }
      if (state === 'running') {
        return route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'job-thumbs',
            kind: 'thumbnails',
            status: 'running',
            total: 4,
            completed: Math.min(jobPolls, 3),
          }),
        })
      }
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job-thumbs',
          kind: 'thumbnails',
          status: 'completed',
          total: 4,
          completed: 4,
        }),
      })
    }

    if (url.pathname === '/api/thumbnails') {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(state === 'completed' ? thumbnailsPayload : { items: [] }),
      })
    }

    if (url.pathname === '/api/clusters') {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(state === 'completed' ? clusterPayload : { items: [] }),
      })
    }

    if (url.pathname === '/api/duplicates') {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(state === 'completed' ? duplicatePayload : { items: [] }),
      })
    }

    return route.fulfill({ status: 404, body: '{}' })
  })
}

async function attachUploads(page) {
  const fileInput = page.locator('input[type="file"]').first()
  await fileInput.setInputFiles([
    {
      name: '20240101T090000_a.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('fake-image-a'),
    },
    {
      name: '20240101T091000_b.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('fake-image-b'),
    },
  ])
}

async function selectStage(page, stageKey) {
  const labels = {
    intake: 'Intake',
    thumbnails: 'Thumbnails',
    clusters: 'Clusters',
    duplicates: 'Duplicates',
  }
  const tabs = page.locator('.stage-tabs')
  if (await tabs.isVisible()) {
    await page.locator('.stage-tabs button').filter({ hasText: labels[stageKey] }).click()
    return
  }
  await page.locator('.stage-select').selectOption(stageKey)
}

test('auto thumbnails and clustering show progress', async ({ page }) => {
  await setupRoutes(page, 'running')
  await page.goto('/')
  await attachUploads(page)

  await expect(page.locator('.progress-title')).toHaveText('Building thumbnails')
  await expect(page.locator('.progress-detail')).toContainText('complete')
})

for (const state of states) {
  test(`visual snapshots - ${state}`, async ({ page }, testInfo) => {
    await setupRoutes(page, state)
    await page.goto('/')

    if (state !== 'empty') {
      await attachUploads(page)
    }

    const stages = ['intake', 'thumbnails', 'clusters', 'duplicates']
    for (const stage of stages) {
      await selectStage(page, stage)
      await page.waitForTimeout(150)
      await expect(page).toHaveScreenshot(
        `${stage}-${state}-${testInfo.project.name}.png`,
      )
    }
  })
}
