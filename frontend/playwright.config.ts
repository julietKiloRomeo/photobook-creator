import { defineConfig, devices } from "@playwright/test";

// E2E specs for shoebox. Selectors use roles and accessible names, not
// CSS IDs (per the v2 test policy).
//
// By default, Playwright starts its own backend (on :8000 with
// frontend/.e2e-data) and frontend (on :5173). For ad-hoc runs against
// an already-running stack (e.g. ox-47's audit stack on :5174/:8001),
// set ``SHOEBOX_E2E_BASE_URL`` to skip the managed webServers entirely.
const externalBaseUrl = process.env.SHOEBOX_E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: externalBaseUrl ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  webServer: externalBaseUrl
    ? undefined
    : [
        {
          command: "uv run shoebox-api --host 127.0.0.1 --port 8000",
          url: "http://127.0.0.1:8000/api/health",
          cwd: "..",
          reuseExistingServer: !process.env.CI,
          env: { SHOEBOX_DATA_DIR: "frontend/.e2e-data" },
          timeout: 30_000,
        },
        {
          command: "npm run dev -- --host 127.0.0.1 --port 5173",
          url: "http://127.0.0.1:5173",
          reuseExistingServer: !process.env.CI,
          timeout: 30_000,
        },
      ],
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 5"] },
    },
  ],
});
