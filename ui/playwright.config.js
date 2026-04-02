import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { browserName: 'chromium', viewport: { width: 1280, height: 720 } },
    },
    {
      name: 'tablet',
      use: { browserName: 'chromium', viewport: { width: 1024, height: 768 } },
    },
    {
      name: 'mobile',
      use: { browserName: 'chromium', ...devices['iPhone 14'] },
    },
  ],
  webServer: [
    {
      command: 'uv run photobook-thumbnails --serve',
      url: 'http://127.0.0.1:8000',
      reuseExistingServer: true,
      cwd: '..',
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 4173',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: true,
    },
  ],
})
