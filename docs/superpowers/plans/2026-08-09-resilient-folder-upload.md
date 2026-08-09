# Resilient Folder Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make photo and recursive-folder uploads observable, HEIC-capable, resilient to bad files, and automatically processed into refreshed stacks on desktop and mobile.

**Architecture:** Keep one multipart request per selection. The backend classifies expected per-file failures, persists valid references, and enqueues one processing job after the batch; the frontend uses `XMLHttpRequest` for transfer progress and polls the returned job. Project photo counts and toolbar activity provide enough state for truthful stack empty states.

**Tech Stack:** FastAPI, Pydantic, Pillow, pillow-heif, SQLite, Svelte 4, TypeScript, Playwright, pytest, uv.

**Issues:** #18, #19, #20, #21

**Worktree:** `/home/jkr/projects/photo-book-creator-wt/dev/18-resilient-upload`

---

## File Map

- `backend/shoebox/pipeline/tier1.py`: register HEIF decoding and convert image decode failures into a domain exception.
- `backend/shoebox/api/schemas.py`: define upload rejection/job response fields and project photo count.
- `backend/shoebox/api/uploads.py`: classify each file independently and enqueue one post-upload processing job.
- `backend/shoebox/store/dao.py`: include reference counts in project reads.
- `pyproject.toml`, `uv.lock`: install `pillow-heif` in production.
- `tests/test_projects_and_uploads.py`: cover HEIC, mixed batches, duplicate/rejection accounting, enqueue count, and photo count.
- `tests/test_processing_flow.py`: exercise automatic initial processing while retaining explicit reprocessing coverage.
- `frontend/src/lib/api.ts`: expose the extended contract and XHR upload progress.
- `frontend/src/lib/components/ProjectToolbar.svelte`: provide photo/folder actions, progress, automatic polling, cancellation guard, and skipped-file disclosure.
- `frontend/src/routes/ProjectScreen.svelte`: refresh project counts and relay activity to the stack screen.
- `frontend/src/routes/StacksScreen.svelte`: load all stacks once and render state-specific empty messages.
- `frontend/e2e/resilient-upload.spec.ts`: cover deterministic progress, mixed recursive folders, automatic stack refresh, failures, keyboard use, and overflow.
- `frontend/e2e/happy-path.spec.ts`, `frontend/e2e/regression-book-text.spec.ts`: remove manual processing from existing flows.
- `frontend/playwright.config.ts`: run the mobile project at the approved 360-pixel width.

## Required Commit Gate

Before every commit in this plan, run the focused tests listed in the task, then run:

```bash
podman run --rm --network=none \
  -v "$PWD:/repo" \
  -v "$PWD/.trufflehog:/tmp" \
  docker.io/trufflesecurity/trufflehog:latest \
  filesystem --exclude-paths=/tmp/exclude.txt /repo
```

Expected: `verified_secrets: 0` and `unverified_secrets: 0`.

### Task 1: Decode HEIC And Classify Decode Failures

**Files:**
- Modify: `pyproject.toml:7-15`
- Modify: `uv.lock`
- Modify: `backend/shoebox/pipeline/tier1.py:1-152`
- Test: `tests/test_projects_and_uploads.py`

- [ ] **Step 1: Add a failing real-HEIC tier-one test**

Add imports and a test that generates a genuine HEIF container at runtime:

```python
from PIL import Image
from pillow_heif import from_pillow

from shoebox.pipeline.tier1 import ingest_file


def test_tier_one_decodes_heic(tmp_path: Path) -> None:
    source = tmp_path / "generated.heic"
    from_pillow(Image.new("RGB", (48, 32), "#845ec2")).save(source, quality=90)

    result = ingest_file(
        source_path=source,
        thumbs_dir=tmp_path / "thumbs",
        medium_dir=tmp_path / "medium",
        thumb_small_width=24,
        thumb_medium_width=40,
    )

    assert (result.width, result.height) == (48, 32)
    assert (tmp_path / "thumbs" / f"{result.file_hash}.jpg").is_file()
    assert (tmp_path / "medium" / f"{result.file_hash}.jpg").is_file()
```

- [ ] **Step 2: Install the dependency and verify the test fails at production decode**

Add to production dependencies:

```toml
"pillow-heif>=0.16",
```

Run:

```bash
uv lock
uv sync --extra dev
uv run pytest tests/test_projects_and_uploads.py::test_tier_one_decodes_heic -v
```

Expected: FAIL because Pillow has no registered HEIF opener.

- [ ] **Step 3: Register HEIF and introduce a narrow domain exception**

In `tier1.py`, import and register the opener once:

```python
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()


class ImageDecodeError(ValueError):
    """The submitted file could not be decoded as an image."""
```

Open and fully decode before metadata or derivative writes:

```python
try:
    with Image.open(source_path) as opened:
        opened.load()
        img = ImageOps.exif_transpose(opened)
except (UnidentifiedImageError, OSError, SyntaxError) as exc:
    raise ImageDecodeError("Image could not be decoded") from exc
```

Keep derivative creation outside this `try` so disk failures remain request-level failures.

- [ ] **Step 4: Verify HEIC and the existing suite**

Run:

```bash
uv run pytest tests/test_projects_and_uploads.py::test_tier_one_decodes_heic -v
uv run pytest -q
uv run ruff check .
```

Expected: PASS; existing 41 tests plus the new test pass.

- [ ] **Step 5: Run the required commit gate and commit**

```bash
git add pyproject.toml uv.lock backend/shoebox/pipeline/tier1.py tests/test_projects_and_uploads.py
git commit -m "feat: decode HEIC photo uploads"
```

### Task 2: Return Per-File Rejections Without Aborting Valid Photos

**Files:**
- Modify: `backend/shoebox/api/schemas.py`
- Modify: `backend/shoebox/api/uploads.py`
- Test: `tests/test_projects_and_uploads.py`

- [ ] **Step 1: Write failing mixed-batch and zero-accepted tests**

Add a mixed request using one valid fixture twice plus corrupt, unsupported, and empty files:

```python
def test_mixed_upload_continues_and_returns_ordered_safe_rejections(
    client: TestClient,
    fixture_pack_dir: Path,
) -> None:
    project = _create_project(client)
    valid = (fixture_pack_dir / "vacation_01.jpg").read_bytes()

    response = client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", ("valid.jpg", valid, "image/jpeg")),
            ("files", ("corrupt.jpg", b"not a jpeg", "image/jpeg")),
            ("files", ("notes.txt", b"text", "text/plain")),
            ("files", ("empty.png", b"", "image/png")),
            ("files", ("duplicate.jpg", valid, "image/jpeg")),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 1
    assert body["duplicates"] == 1
    assert body["rejected"] == [
        {"filename": "corrupt.jpg", "reason": "file could not be decoded"},
        {"filename": "notes.txt", "reason": "unsupported file type"},
        {"filename": "empty.png", "reason": "file is empty"},
    ]
    assert "not a jpeg" not in response.text
```

Also add a rejected-only request asserting HTTP 201, zero accepted, zero duplicates, an empty `references` list, and all rejection reasons.

- [ ] **Step 2: Run the tests to confirm batch abortion**

```bash
uv run pytest tests/test_projects_and_uploads.py -k "mixed_upload or rejected_only" -v
```

Expected: FAIL because corrupt image decoding aborts the request and the response lacks `rejected`.

- [ ] **Step 3: Extend the strict response schema**

In `api/schemas.py`:

```python
from typing import Literal


class UploadRejection(BaseModel):
    filename: str
    reason: Literal[
        "unsupported file type",
        "file could not be decoded",
        "file is empty",
    ]


class UploadResult(BaseModel):
    accepted: int
    duplicates: int
    references: list[Reference]
    rejected: list[UploadRejection]
    job_id: str | None
```

- [ ] **Step 4: Process expected file failures independently**

In `api/uploads.py`, import `ImageDecodeError` and `UploadRejection`, then add:

```python
_SUPPORTED_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
)


def _safe_filename(filename: str | None) -> str:
    basename = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return basename or "unnamed file"
```

For each upload, read content, reject empty content first, reject extensions outside the allowlist second, and catch only `ImageDecodeError` around `ingest_file`. Append `UploadRejection` in input order and continue. Leave database, move, and derivative-write exceptions uncaught. Return:

```python
return UploadResult(
    accepted=len(accepted_refs),
    duplicates=duplicates,
    references=[_to_reference(row) for row in accepted_refs],
    rejected=rejected,
    job_id=None,
)
```

Move the original file only after confirming `_find_existing_id(...) is None`; this avoids an unused duplicate original with a second extension.

- [ ] **Step 5: Verify response behavior and lint**

```bash
uv run pytest tests/test_projects_and_uploads.py -v
uv run ruff check backend tests
```

Expected: PASS, including valid mixed-batch persistence and safe ordered reasons.

- [ ] **Step 6: Run the required commit gate and commit**

```bash
git add backend/shoebox/api/schemas.py backend/shoebox/api/uploads.py tests/test_projects_and_uploads.py
git commit -m "feat: preserve valid files in mixed uploads"
```

### Task 3: Enqueue Exactly One Automatic Processing Job

**Files:**
- Modify: `backend/shoebox/api/uploads.py`
- Modify: `tests/test_projects_and_uploads.py`
- Modify: `tests/test_processing_flow.py`

- [ ] **Step 1: Write failing enqueue-count tests**

Patch the singleton runner and record calls:

```python
calls: list[tuple[str, str]] = []


def fake_enqueue(*, project_id: str, kind: str) -> dict:
    calls.append((project_id, kind))
    return {"id": "j_once"}


monkeypatch.setattr(get_runner(), "enqueue", fake_enqueue)
```

Add one test uploading two unique valid photos and assert:

```python
assert response.json()["job_id"] == "j_once"
assert calls == [(project["id"], "process")]
```

Add one test that first accepts a photo, clears `calls`, then submits a duplicate-only batch and a rejected-only batch. Assert `job_id is None` and `calls == []` for both zero-accepted requests.

- [ ] **Step 2: Confirm the response never enqueues**

```bash
uv run pytest tests/test_projects_and_uploads.py -k "enqueue" -v
```

Expected: FAIL because `job_id` is always null.

- [ ] **Step 3: Enqueue once after the complete loop**

Import `get_runner` and add after all files have been processed:

```python
job_id: str | None = None
if accepted_refs:
    job = get_runner().enqueue(project_id=project_id, kind="process")
    job_id = job["id"]
```

Return `job_id=job_id`. Never enqueue inside the file loop.

- [ ] **Step 4: Change initial processing integration tests to use the upload job**

For each first processing run in `test_processing_flow.py`:

```python
upload = _upload_all(client, project_id, fixture_pack_dir)
assert upload["job_id"] is not None
finished = _wait_for_job(client, upload["job_id"])
assert finished["status"] == "completed", finished
```

Keep explicit `POST /process` only where a test intentionally reprocesses an already processed project.

- [ ] **Step 5: Verify upload and processing flows**

```bash
uv run pytest tests/test_projects_and_uploads.py tests/test_processing_flow.py -v
uv run pytest -q
uv run ruff check .
```

Expected: PASS; automatic initial processing produces stacks and themes.

- [ ] **Step 6: Run the required commit gate and commit**

```bash
git add backend/shoebox/api/uploads.py tests/test_projects_and_uploads.py tests/test_processing_flow.py
git commit -m "feat: process accepted uploads automatically"
```

### Task 4: Expose Project Photo Counts

**Files:**
- Modify: `backend/shoebox/store/dao.py:35-51`
- Modify: `backend/shoebox/api/schemas.py:16-20`
- Modify: `frontend/src/lib/api.ts:37-42`
- Test: `tests/test_projects_and_uploads.py`

- [ ] **Step 1: Write a failing project-count test**

```python
def test_project_photo_count_tracks_unique_references(
    client: TestClient,
    fixture_pack_dir: Path,
) -> None:
    project = _create_project(client)
    photo = (fixture_pack_dir / "vacation_01.jpg").read_bytes()

    assert project["photo_count"] == 0

    client.post(
        f"/api/projects/{project['id']}/uploads",
        files=[
            ("files", ("first.jpg", photo, "image/jpeg")),
            ("files", ("duplicate.jpg", photo, "image/jpeg")),
        ],
    )

    refreshed = client.get(f"/api/projects/{project['id']}").json()
    assert refreshed["photo_count"] == 1
```

- [ ] **Step 2: Run the test to confirm the field is absent**

```bash
uv run pytest tests/test_projects_and_uploads.py::test_project_photo_count_tracks_unique_references -v
```

Expected: FAIL with missing `photo_count`.

- [ ] **Step 3: Count references in project reads**

Replace project reads in `dao.py` with a correlated count:

```sql
SELECT p.*,
       (SELECT COUNT(*) FROM references_ AS r WHERE r.project_id = p.id) AS photo_count
FROM projects AS p
```

Apply `WHERE p.id = ?` in `get_project` and `ORDER BY p.created_at DESC` in `list_projects`. Add `photo_count: int` to the backend `Project` model and frontend `Project` type.

- [ ] **Step 4: Verify backend and frontend contracts**

```bash
uv run pytest tests/test_projects_and_uploads.py -v
uv run ruff check backend tests
cd frontend && npm run check && npm run build
```

Expected: PASS.

- [ ] **Step 5: Run the required commit gate and commit**

Run the gate from the repository root, then:

```bash
git add backend/shoebox/store/dao.py backend/shoebox/api/schemas.py frontend/src/lib/api.ts tests/test_projects_and_uploads.py
git commit -m "feat: expose project photo counts"
```

### Task 5: Show Transfer Progress And Poll Automatic Processing

**Files:**
- Modify: `frontend/src/lib/api.ts:54-140`
- Modify: `frontend/src/lib/components/ProjectToolbar.svelte`
- Create: `frontend/e2e/resilient-upload.spec.ts`

- [ ] **Step 1: Write a deterministic failing browser test**

Create a project, inject a fake `XMLHttpRequest` with `page.addInitScript`, and emit progress at 50%, 100%, then a 201 response:

```ts
this.upload.onprogress?.(new ProgressEvent("progress", {
  lengthComputable: true,
  loaded: 50,
  total: 100,
}));
```

Return:

```json
{"accepted":1,"duplicates":0,"references":[],"rejected":[],"job_id":"j_fake_progress"}
```

Route `**/api/jobs/j_fake_progress` to return one running job and then a completed job. Assert the accessible upload progressbar has value `50`, `Finishing upload…` appears at 100%, processing status appears after the upload response, and `Added 1` remains visible after completion.

- [ ] **Step 2: Run the browser test to confirm missing UI and selectors**

```bash
cd frontend
npx playwright test e2e/resilient-upload.spec.ts --project=chromium-desktop
```

Expected: FAIL because `uploadFiles` uses fetch and the toolbar has no progressbar.

- [ ] **Step 3: Replace only the upload API transport with XHR**

Add strict `UploadRejection`, `UploadProgress`, extended `UploadResult`, then implement:

```ts
uploadFiles: (projectId, files, onProgress): Promise<UploadResult> => {
  const form = new FormData();
  for (const file of files) form.append("files", file);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/projects/${projectId}/uploads`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.({ loaded: event.loaded, total: event.total });
      }
    };
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(xhr.status, xhr.responseText || xhr.statusText));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as UploadResult);
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(new TypeError("Failed to fetch"));
    xhr.onabort = () => reject(new DOMException("The operation was aborted.", "AbortError"));
    xhr.send(form);
  });
},
```

- [ ] **Step 4: Merge upload and processing state in the toolbar**

Use `phase: "idle" | "uploading" | "processing"`, byte progress, returned `job_id`, and the existing 400ms polling interval. At 100% label the transfer `Finishing upload…`; do not switch to processing until the 201 response arrives. Preserve `uploadSummary` when polling fails. Add an `onDestroy` generation guard so stale polling cannot dispatch after navigation.

Render native `<progress>` elements with `aria-label="Upload progress"` and `aria-label="Photo organizing progress"`. Replace **Upload photos** with **Add photos** and remove **Process new photos**.

- [ ] **Step 5: Verify deterministic state transitions and frontend checks**

```bash
cd frontend
npx playwright test e2e/resilient-upload.spec.ts --project=chromium-desktop
npm run check
npm run build
```

Expected: PASS.

- [ ] **Step 6: Run the required commit gate and commit**

Run the gate from the repository root, then:

```bash
git add frontend/src/lib/api.ts frontend/src/lib/components/ProjectToolbar.svelte frontend/e2e/resilient-upload.spec.ts
git commit -m "feat: show upload and processing progress"
```

### Task 6: Add Recursive Folder Selection And Skipped-File Disclosure

**Files:**
- Modify: `frontend/src/lib/components/ProjectToolbar.svelte`
- Modify: `frontend/e2e/resilient-upload.spec.ts`
- Modify: `frontend/playwright.config.ts`

- [ ] **Step 1: Add a failing recursive-folder browser test**

At runtime, create a temporary nested directory containing two copied fixture JPEGs, `notes.txt`, and `broken.jpg`. Click **Add folder**, pass the directory to the Playwright file chooser, and assert:

```ts
await expect(page.getByText(/added\s+2/i)).toBeVisible({ timeout: 30_000 });
await expect(page.getByText(/2 skipped files/i)).toBeVisible();
await page.getByText(/2 skipped files/i).press("Enter");
await expect(page.getByText("notes.txt", { exact: true })).toBeVisible();
await expect(page.getByText("broken.jpg", { exact: true })).toBeVisible();
```

Click **All**, wait for the stack list, then assert:

```ts
expect(await page.evaluate(
  () => document.documentElement.scrollWidth > window.innerWidth,
)).toBe(false);
```

Delete the temporary directory in `finally`.

- [ ] **Step 2: Confirm folder action and disclosure are absent**

```bash
cd frontend
npx playwright test e2e/resilient-upload.spec.ts --project=chromium-desktop
```

Expected: FAIL because **Add folder** is absent.

- [ ] **Step 3: Add folder selection without weakening TypeScript checks**

Add a Svelte action because the framework type does not declare `webkitdirectory`:

```ts
function directory(node: HTMLInputElement) {
  node.setAttribute("webkitdirectory", "");
  return { destroy: () => node.removeAttribute("webkitdirectory") };
}
```

Use separate hidden photo and folder inputs, both with:

```ts
const ACCEPT = "image/jpeg,image/png,image/gif,image/webp,image/bmp,image/tiff,image/heic,image/heif,.heic,.heif";
```

Filter folder entries by a matching extension set because `File.type` may be empty. If every file is filtered, skip the HTTP request and produce a zero-accepted summary. Merge client rejections before server rejections.

- [ ] **Step 4: Render an accessible responsive summary**

Use native `<details><summary>` for skipped files, an ordered or unordered list of filename/reason pairs, and `overflow-wrap: anywhere`. Use a two-column `.actions` grid, full-width status rows, and collapse actions below 320px. Do not announce every progress tick through `aria-live`; limit the polite live region to completion summary.

Set the Playwright mobile project to an explicit viewport:

```ts
use: { ...devices["Pixel 5"], viewport: { width: 360, height: 800 } }
```

- [ ] **Step 5: Verify desktop, 360px mobile, keyboard, and Svelte diagnostics**

```bash
cd frontend
npx playwright test e2e/resilient-upload.spec.ts --project=chromium-desktop
npx playwright test e2e/resilient-upload.spec.ts --project=chromium-mobile
npm run check
npm run build
```

Expected: PASS with no horizontal overflow and keyboard-operable disclosure.

- [ ] **Step 6: Run the required commit gate and commit**

Run the gate from the repository root, then:

```bash
git add frontend/src/lib/components/ProjectToolbar.svelte frontend/e2e/resilient-upload.spec.ts frontend/playwright.config.ts
git commit -m "feat: upload recursive photo folders"
```

### Task 7: Refresh Stacks And Make Empty States Truthful

**Files:**
- Modify: `frontend/src/routes/ProjectScreen.svelte`
- Modify: `frontend/src/routes/StacksScreen.svelte`
- Modify: `frontend/e2e/happy-path.spec.ts`
- Modify: `frontend/e2e/regression-book-text.spec.ts`
- Modify: `frontend/e2e/resilient-upload.spec.ts`

- [ ] **Step 1: Write failing empty-state and automatic-refresh assertions**

Add browser assertions for:

```ts
await expect(page.getByText(/no photos yet/i)).toBeVisible();
```

During a delayed fake upload/job:

```ts
await expect(page.getByText(/stacks will appear automatically/i)).toBeVisible();
```

After real folder processing, assert the stack list appears without reload or manual processing. Switch to **Pending** after all stacks auto-resolve and assert a **View All** action appears rather than an upload/process instruction.

- [ ] **Step 2: Confirm current empty copy conflates states**

```bash
cd frontend
npx playwright test e2e/resilient-upload.spec.ts --project=chromium-desktop
```

Expected: FAIL on the new state-specific messages or automatic refresh.

- [ ] **Step 3: Relay toolbar activity and refresh project metadata**

Dispatch `activity: { phase }` whenever toolbar phase changes. In `ProjectScreen.svelte`, refresh the project after `uploaded`, increment `dataVersion`, and pass `photoCount` plus `processingActive` into `StacksScreen`.

```svelte
<ProjectToolbar
  {projectId}
  on:uploaded={handleUploaded}
  on:processed={bump}
  on:activity={handleActivity}
/>
```

- [ ] **Step 4: Load all stacks once and derive the active filter**

Replace status-specific requests with one `api.listStacks(projectId)` request. Derive visible stacks locally and remove the duplicate `onMount` plus reactive fetch triggers. Render empty states in this order: zero photos, active upload/processing, pending empty with resolved stacks, no matches.

```ts
$: stacks = filter === "all"
  ? allStacks
  : allStacks.filter((stack) => stack.status === filter);
$: hasResolvedStacks = allStacks.some((stack) => stack.status === "resolved");
```

- [ ] **Step 5: Update existing E2E flows**

In both existing specs, select **Add photos**, remove the **Process new photos** click, and wait for the stack list or completion state produced by automatic processing. Keep explicit processing only in backend tests covering intentional reprocessing.

- [ ] **Step 6: Run all browser and static frontend checks**

```bash
cd frontend
npm run check
npm run build
npx playwright test
```

Expected: all desktop and mobile projects pass.

- [ ] **Step 7: Run the required commit gate and commit**

Run the gate from the repository root, then:

```bash
git add frontend/src/routes/ProjectScreen.svelte frontend/src/routes/StacksScreen.svelte frontend/e2e/happy-path.spec.ts frontend/e2e/regression-book-text.spec.ts frontend/e2e/resilient-upload.spec.ts
git commit -m "fix: refresh stacks after automatic processing"
```

### Task 8: Final Integrated Verification And GitHub Handoff

**Files:**
- Modify only files required by failures found during verification.
- Update GitHub issues #18, #19, #20, and #21 with evidence; do not create a local report.

- [ ] **Step 1: Run the complete backend gate**

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
```

Expected: all tests and lint pass.

- [ ] **Step 2: Run the complete frontend gate**

```bash
cd frontend
npm install
npm run check
npm run build
npx playwright test
```

Expected: all desktop and 360px mobile tests pass.

- [ ] **Step 3: Run the final secrets scan**

Run the Required Commit Gate command. Expected: zero verified and unverified secrets.

- [ ] **Step 4: Inspect the complete branch**

```bash
git status --short
git diff main...HEAD --check
git diff --stat main...HEAD
git log --oneline main..HEAD
```

Expected: no unintended generated files; only upload-flow changes and tests are present.

- [ ] **Step 5: Post test evidence and implementation notes**

Post concise comments to issues #18–#21 listing the relevant commits, backend count, browser projects, responsive result, and secrets-scan result. Request `frontend-test-agent` validation through the issue workflow before merge.

## Residual Risk

If job enqueueing fails after accepted references commit, retrying the same bytes produces duplicates and no automatic job under the approved zero-accepted rule. The existing `POST /process` API remains available for recovery. Transactional job/outbox semantics are intentionally excluded from #18–#21 and should become a separate issue if production deployment requires crash-safe background work.
