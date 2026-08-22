import { expect, test, type Page } from "@playwright/test";
import { promises as fs } from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_DIR = path.resolve(HERE, "..", "..", "tests", "fixtures", "vacation-20");

type FakeUpload =
  | {
      kind: "success";
      controlled?: boolean;
      body: {
        accepted: number;
        duplicates: number;
        references: [];
        rejected: [];
        job_id: string | null;
      };
    }
  | { kind: "http"; status: number; statusText: string; responseText: string }
  | { kind: "network" };

async function installFakeUpload(page: Page, configuration: FakeUpload) {
  await page.addInitScript((fakeUpload) => {
    const NativeXMLHttpRequest = window.XMLHttpRequest;
    const pendingUploads: Array<() => void> = [];

    class FakeUploadRequest extends EventTarget {
      readonly upload = new EventTarget();
      status = 0;
      statusText = "";
      responseText = "";
      private method = "";
      private url = "";
      private headers: Array<[string, string]> = [];

      open(method: string, url: string | URL) {
        this.method = method;
        this.url = String(url);
      }

      setRequestHeader(name: string, value: string) {
        this.headers.push([name, value]);
      }

      send(body?: Document | XMLHttpRequestBodyInit | null) {
        if (this.method !== "POST" || !/\/api\/projects\/[^/]+\/uploads(\?|$)/.test(this.url)) {
          const request = new NativeXMLHttpRequest();
          request.open(this.method, this.url);
          for (const [name, value] of this.headers) request.setRequestHeader(name, value);
          request.addEventListener("load", () => {
            this.status = request.status;
            this.statusText = request.statusText;
            this.responseText = request.responseText;
            this.dispatchEvent(new ProgressEvent("load"));
          });
          request.addEventListener("error", () => this.dispatchEvent(new ProgressEvent("error")));
          request.addEventListener("abort", () => this.dispatchEvent(new ProgressEvent("abort")));
          request.send(body);
          return;
        }

        const finish = () => {
          if (fakeUpload.kind === "network") {
            this.dispatchEvent(new ProgressEvent("error"));
            return;
          }
          if (fakeUpload.kind === "http") {
            this.status = fakeUpload.status;
            this.statusText = fakeUpload.statusText;
            this.responseText = fakeUpload.responseText;
          } else {
            this.status = 201;
            this.statusText = "Created";
            this.responseText = JSON.stringify(fakeUpload.body);
          }
          this.dispatchEvent(new ProgressEvent("load"));
        };

        const emitProgress = (loaded: number) =>
          this.upload.dispatchEvent(
            new ProgressEvent("progress", { lengthComputable: true, loaded, total: 100 }),
          );

        if (fakeUpload.kind === "success" && fakeUpload.controlled) {
          emitProgress(50);
          pendingUploads.push(() => emitProgress(100), finish);
          return;
        }

        emitProgress(fakeUpload.kind === "success" ? 100 : 50);
        finish();
      }
    }

    Object.defineProperty(window, "XMLHttpRequest", { value: FakeUploadRequest });
    Object.defineProperty(window, "__advanceUpload", {
      value: () => pendingUploads.shift()?.(),
    });
  }, configuration);
}

/** Chunked uploads defer tier-2, so the toolbar's job comes from ``/process``. */
async function stubProcessJob(page: Page, jobId: string) {
  await page.route("**/api/projects/*/process", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        id: jobId,
        project_id: "p_fake",
        kind: "process",
        status: "queued",
        progress: 0,
        message: null,
        error: null,
      }),
    });
  });
}

async function createProject(page: Page, name: string) {
  await page.getByPlaceholder("Italy 2026").fill(name);
  await page.getByRole("button", { name: /^create$/i }).click();
  await expect(page.getByRole("button", { name: "Stacks", exact: true })).toBeVisible();
  const match = page.url().match(/#\/p\/([^/]+)/);
  expect(match).not.toBeNull();
  return match![1];
}

function fixturePhotos(count: number) {
  return Array.from({ length: count }, (_, index) =>
    path.join(FIXTURE_DIR, `vacation_${String(index + 1).padStart(2, "0")}.jpg`),
  );
}

function countUploadAndProcessRequests(page: Page) {
  const counts = { uploads: 0, processes: 0 };
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const { pathname } = new URL(request.url());
    if (pathname.endsWith("/uploads")) counts.uploads += 1;
    if (pathname.endsWith("/process")) counts.processes += 1;
  });
  return counts;
}

async function addPhotos(page: Page, files: string[]) {
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: "Add photos" }).click(),
  ]);
  await chooser.setFiles(files);
}

async function addSyntheticPhoto(page: Page, name = "moment.jpg") {
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.getByRole("button", { name: "Add photos" }).click(),
  ]);
  await chooser.setFiles({ name, mimeType: "image/jpeg", buffer: Buffer.from("jpg") });
}

test("cancels project activity when client-side navigation reuses the toolbar", async ({ page }) => {
  await installFakeUpload(page, {
    kind: "success",
    body: {
      accepted: 1,
      duplicates: 0,
      references: [],
      rejected: [],
      job_id: null,
    },
  });
  await stubProcessJob(page, "j_project_a");

  await page.goto("/");
  const suffix = Date.now();
  const projectAName = `Project A ${suffix}`;
  const projectBName = `Project B ${suffix}`;
  const projectA = await createProject(page, projectAName);
  await page.getByRole("link", { name: "shoebox home" }).click();
  const projectB = await createProject(page, projectBName);

  let releaseJob!: () => void;
  let markJobFulfilled!: () => void;
  const jobRelease = new Promise<void>((resolve) => (releaseJob = resolve));
  const jobFulfilled = new Promise<void>((resolve) => (markJobFulfilled = resolve));
  await page.route("**/api/jobs/j_project_a", async (route) => {
    await jobRelease;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "j_project_a",
        project_id: projectA,
        kind: "process",
        status: "completed",
        progress: 1,
        message: "Ready",
        error: null,
      }),
    });
    markJobFulfilled();
  });

  await page.evaluate((id) => {
    window.location.hash = `/p/${id}`;
  }, projectA);
  await expect(page.getByTitle(projectAName)).toBeVisible();
  await expect(page.getByText("No photos yet. Add photos or a folder to begin.")).toBeVisible();

  await addSyntheticPhoto(page, "project-a.jpg");
  await expect(page.getByRole("progressbar", { name: "Photo organizing progress" })).toBeVisible();
  await page.waitForRequest("**/api/jobs/j_project_a");

  let projectBStackRequests = 0;
  await page.route(`**/api/projects/${projectB}/stacks*`, async (route) => {
    projectBStackRequests += 1;
    await route.continue();
  });
  await Promise.all([
    page.waitForResponse((response) =>
      response.url().includes(`/api/projects/${projectB}/stacks`),
    ),
    page.evaluate((id) => {
      window.location.hash = `/p/${id}`;
    }, projectB),
  ]);
  await expect(page.getByTitle(projectBName)).toBeVisible();
  await expect(page.getByText("No photos yet. Add photos or a folder to begin.")).toBeVisible();
  const stackRequestsAfterNavigation = projectBStackRequests;

  releaseJob();
  await jobFulfilled;
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );

  await expect(page.getByRole("button", { name: "Add photos" })).toBeEnabled();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  await expect(page.getByText("Added 1")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("Photos are being organized. Stacks will appear automatically.")).toHaveCount(0);
  expect(projectBStackRequests).toBe(stackRequestsAfterNavigation);
});

test("shows upload progress before automatically organizing accepted photos", async ({ page }) => {
  await installFakeUpload(page, {
    kind: "success",
    controlled: true,
    body: {
      accepted: 1,
      duplicates: 0,
      references: [],
      rejected: [],
      job_id: null,
    },
  });
  await stubProcessJob(page, "j_fake_progress");

  let jobRequests = 0;
  await page.route("**/api/jobs/j_fake_progress", async (route) => {
    jobRequests += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "j_fake_progress",
        project_id: "p_fake",
        kind: "process",
        status: jobRequests <= 2 ? "running" : "completed",
        progress: jobRequests <= 2 ? 0.4 : 1,
        message: jobRequests <= 2 ? "Grouping moments" : "Ready",
        error: null,
      }),
    });
  });

  await page.goto("/");
  await page.getByPlaceholder("Italy 2026").fill(`Progress ${Date.now()}`);
  await page.getByRole("button", { name: /^create$/i }).click();
  await expect(page.getByRole("button", { name: "Stacks", exact: true })).toBeVisible();
  await expect(page.getByText("No photos yet. Add photos or a folder to begin.")).toBeVisible();
  await page.getByRole("button", { name: "Themes", exact: true }).click();
  await expect(
    page.getByText(
      "No themes yet. Themes appear automatically after photos are organized. You can also add one above.",
    ),
  ).toBeVisible();
  await expect(page.getByText(/Process new photos/i)).toHaveCount(0);
  await page.getByRole("button", { name: "Stacks", exact: true }).click();

  await addSyntheticPhoto(page);

  const uploadProgress = page.getByRole("progressbar", { name: "Upload progress" });
  await expect(uploadProgress).toHaveAttribute("value", "50");
  await expect(page.getByText("0 of 1 files uploaded")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Photo organizing progress" })).toHaveCount(0);

  await page.evaluate(() => (window as unknown as { __advanceUpload(): void }).__advanceUpload());
  await expect(uploadProgress).toHaveAttribute("value", "100");
  await expect(page.getByText("Finishing upload…")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Photo organizing progress" })).toHaveCount(0);

  await page.route(/\/api\/projects\/[^/]+$/, async (route) => {
    const response = await route.fetch();
    const project = await response.json();
    await route.fulfill({ response, json: { ...project, photo_count: 1 } });
  });
  await page.evaluate(() => (window as unknown as { __advanceUpload(): void }).__advanceUpload());
  const organizingProgress = page.getByRole("progressbar", { name: "Photo organizing progress" });
  await expect(organizingProgress).toBeVisible();
  await expect(
    page.getByText("Photos are being organized. Stacks will appear automatically."),
  ).toBeVisible();
  await expect(page.getByText(/Grouping moments.*40%/i)).toBeVisible();
  await expect(organizingProgress).toBeHidden({ timeout: 2_000 });
  await expect(page.getByText("Added 1")).toBeVisible();
  expect(jobRequests).toBe(3);
});

test("keeps the upload summary and actions usable when processing fails", async ({ page }) => {
  await installFakeUpload(page, {
    kind: "success",
    body: {
      accepted: 1,
      duplicates: 0,
      references: [],
      rejected: [],
      job_id: null,
    },
  });
  await stubProcessJob(page, "j_fake_failure");

  let jobRequests = 0;
  await page.route("**/api/jobs/j_fake_failure", async (route) => {
    jobRequests += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "j_fake_failure",
        project_id: "p_fake",
        kind: "process",
        status: "failed",
        progress: 0.6,
        message: "Could not organize photos",
        error: "Photo organizing failed safely",
      }),
    });
  });

  await page.goto("/");
  await createProject(page, `Processing failure ${Date.now()}`);
  await addSyntheticPhoto(page, "processing-failure.jpg");
  await expect(page.getByRole("progressbar", { name: "Photo organizing progress" })).toBeVisible();
  await page.getByRole("tab", { name: "All", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("Photo organizing failed safely");
  await expect(page.getByText("Added 1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add photos" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Add folder" })).toBeEnabled();
  await expect(page.getByRole("progressbar", { name: "Photo organizing progress" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "All", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(jobRequests).toBe(1);
});

test("recovers from an upload HTTP error without polling a job", async ({ page }) => {
  await installFakeUpload(page, {
    kind: "http",
    status: 503,
    statusText: "Service Unavailable",
    responseText: "Upload service unavailable",
  });
  let jobRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/jobs/")) jobRequests += 1;
  });

  await page.goto("/");
  await createProject(page, `HTTP failure ${Date.now()}`);
  await addSyntheticPhoto(page, "http-failure.jpg");

  await expect(page.getByRole("alert")).toHaveText("Upload service unavailable");
  await expect(page.getByText(/^Added /)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add photos" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Add folder" })).toBeEnabled();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  expect(jobRequests).toBe(0);
});

test("recovers from an upload network error without stale progress", async ({ page }) => {
  await installFakeUpload(page, { kind: "network" });

  await page.goto("/");
  await createProject(page, `Network failure ${Date.now()}`);
  await addSyntheticPhoto(page, "network-failure.jpg");

  await expect(page.getByRole("alert")).toHaveText("Failed to fetch");
  await expect(page.getByText(/^Added /)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add photos" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Add folder" })).toBeEnabled();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
});

test("uploads a large batch in chunks and organizes it exactly once", async ({ page }) => {
  await page.goto("/");
  await createProject(page, `Chunked ${Date.now()}`);
  const requests = countUploadAndProcessRequests(page);

  await addPhotos(page, fixturePhotos(12));

  await expect(page.getByRole("progressbar", { name: "Upload progress" })).toBeVisible();
  await expect(page.getByText(/of 12 files uploaded$/)).toBeVisible();
  await expect(page.getByText("Added 12 · 0 duplicates")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Add photos" })).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);

  expect(requests.uploads).toBe(2);
  expect(requests.processes).toBe(1);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("keeps the chunks that landed when a later chunk fails", async ({ page }) => {
  await page.goto("/");
  const projectId = await createProject(page, `Partial ${Date.now()}`);
  const requests = countUploadAndProcessRequests(page);
  await page.route("**/api/projects/*/uploads*", async (route) => {
    if (requests.uploads === 2) {
      await route.fulfill({
        status: 503,
        contentType: "text/plain",
        body: "Upload service unavailable",
      });
      return;
    }
    await route.continue();
  });

  await addPhotos(page, fixturePhotos(12));

  await expect(page.getByRole("alert")).toHaveText("Upload service unavailable", {
    timeout: 30_000,
  });
  await expect(page.getByText("Added 10 · 0 duplicates · 2 files not uploaded")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add photos" })).toBeEnabled({ timeout: 30_000 });

  expect(requests.uploads).toBe(2);
  expect(requests.processes).toBe(1);
  const project = await page.request.get(`/api/projects/${projectId}`);
  expect((await project.json()).photo_count).toBe(10);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("uploads a nested folder and explains every skipped file", async ({ page }) => {
  const uploadFolder = await fs.mkdtemp(path.join(os.tmpdir(), "shoebox-folder-"));
  const nestedFolder = path.join(uploadFolder, "nested");
  const longFilename = `${"summer-memory-".repeat(12)}.jpg`;

  try {
    await fs.mkdir(nestedFolder);
    await Promise.all([
      fs.copyFile(path.join(FIXTURE_DIR, "vacation_01.jpg"), path.join(uploadFolder, longFilename)),
      fs.copyFile(path.join(FIXTURE_DIR, "vacation_02.jpg"), path.join(nestedFolder, "nested-photo.jpg")),
      fs.writeFile(path.join(nestedFolder, "notes.txt"), "not a photo"),
      fs.writeFile(path.join(uploadFolder, "broken.jpg"), "not jpeg data"),
    ]);

    await page.goto("/");
    await page.getByPlaceholder("Italy 2026").fill(`Folder ${Date.now()}`);
    await page.getByRole("button", { name: /^create$/i }).click();
    await expect(page.getByRole("button", { name: "Stacks", exact: true })).toBeVisible();

    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: "Add folder" }).click(),
    ]);
    await chooser.setFiles(uploadFolder);

    await expect(page.getByText(/added\s+2/i)).toBeVisible({ timeout: 30_000 });
    const skippedSummary = page.getByText("2 skipped files", { exact: true });
    await expect(skippedSummary).toBeVisible();
    await skippedSummary.focus();
    await expect(skippedSummary).toBeFocused();
    await skippedSummary.press("Enter");
    await expect(page.getByText("notes.txt", { exact: true })).toBeVisible();
    await expect(page.getByText("unsupported file type", { exact: true })).toBeVisible();
    await expect(page.getByText("broken.jpg", { exact: true })).toBeVisible();
    await expect(page.getByText("file could not be decoded", { exact: true })).toBeVisible();

    await expect(page.getByRole("button", { name: "Add folder" })).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByText("Organizing complete — nothing is pending.")).toBeVisible({
      timeout: 30_000,
    });
    const viewAll = page.getByRole("button", { name: "View All" });
    await viewAll.focus();
    await expect(viewAll).toBeFocused();
    await viewAll.press("Enter");
    await expect(page.getByRole("list", { name: /stacks/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("list", { name: /stacks/i }).locator("li").first()).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  } finally {
    await fs.rm(uploadFolder, { recursive: true, force: true });
  }
});
