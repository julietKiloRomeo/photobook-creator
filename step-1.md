# Step 1 — M1 Vertical Slice MVP

**Product name**: **shoebox** — the family shoebox of photos everyone reaches into. Deploys to `shoebox.valhalla` in M4.

**Goal**: a single user can produce a JSON export end-to-end on a polished, mobile-first UI, using the v2 architecture.

This step establishes the foundation: project structure, backend skeleton, frontend skeleton, the three core screens, the AI pipeline (tiered), and the JSON export. No multi-user, no voting, no Duel, no Timeline yet — those land in M2/M3.

## Test policy (read this first)

All v1 tests are archived and **not inherited**. They are heavily implementation-coupled (asserting on `/api/intake/references`, `chapters`, `operations`, `cluster_state.state`, `needs_review`, `previous_pick_reference_id`, the `darkroom_v2.html` DOM, etc.) — every one of those is a v1 implementation detail we are explicitly removing. Importing them would silently re-anchor v2 to v1's shape.

v2 tests are written **fresh, against intent**, not against v1 mechanics. Concretely:

- Tests describe **user-visible outcomes**, not internal field names.
- Tests target the **v2 API contract** (defined in §4 below) only.
- The vacation-20 fixture pack is reused — it's pure data, not implementation.
- A test that needs to assert on an internal data shape is a smell; prefer driving through the API.
- Goal: every assertion in v2's test suite would still make sense if we swapped SQLite for Postgres, or Svelte for React, without rewriting the tests.

The only artifacts mined from `archive/v1/tests/` for v2 are:
- `tests/fixtures/vacation-20/` (images + manifest).
- The fixture *generator* script (`scripts/generate_vacation_fixture_pack.py`), if/when we need to regenerate it.

## Definition of done

A non-technical user, on a phone or laptop, can:

1. Open the app at a local URL.
2. Create a project ("Italy 2026").
3. Upload a folder of photos.
4. See dedup happen instantly; thumbnails appear.
5. Tap "Process new photos"; stacks and themes appear within a reasonable wait (target: <60s for the 20-photo vacation fixture).
6. Review stacks; pick a best shot per stack.
7. Review themes; rename and drag stacks between them.
8. Open the Book; auto-build a draft; tweak one page; add one text block.
9. Tap Export; receive a folder with `book.json` + `assets/`.

All of the above is covered by automated tests using the vacation-20 fixture.

## Scope (in)

- Project create / list / open.
- Folder upload (multi-file, large-set tolerant) with progress.
- Tier-1 processing on upload: SHA-256 hash, EXIF parse, pHash, thumbnails (small + medium).
- Tier-2 processing on demand: burst clustering (EXIF + camera), visual clustering (local CLIP), theme proposal (clustering + naming).
- Tier-3 optional, off by default in M1.
- Stacks screen (mobile-first list + desktop grid; single-tap pick).
- Themes screen (collapsible mobile sections + desktop columns; drag stacks).
- Book screen (theme picker → pages → single layout template in M1 + text blocks).
- Auto-build draft book button.
- Export endpoint and downloadable bundle.
- One end-to-end test on the vacation-20 fixture.

## Scope (out — explicitly deferred)

- Multi-user, identity, roles, presence (M2).
- Voting, Duel mode (M3).
- Timeline lens (M4).
- Multiple layout templates beyond one (M4).
- Cloud LLM theme naming (M4).
- Docker / Traefik deploy (M4).
- Vendor export converters (M5).

## Tasks

### 1. Project scaffolding

- [ ] New `pyproject.toml` (FastAPI, uvicorn, sqlite, Pillow, open_clip_torch, imagehash, pydantic, pytest). Use `uv` only.
- [ ] New `package.json` for the frontend (Svelte + Vite + TypeScript). Vite dev server proxies `/api/*` to FastAPI.
- [ ] Top-level layout:
  - `backend/` — FastAPI app, SQLite layer, pipeline, export.
  - `frontend/` — Svelte + Vite app.
  - `scripts/` — fixture generator (mined from `archive/v1/scripts/`), pre-push.
  - `tests/` — Python pytest (backend + integration) and Playwright (E2E).
  - `data/` — runtime data, `.gitignore`d (`projects/<id>/{originals,thumbs,medium,embeddings}`).
- [ ] Migrate the vacation-20 fixture pack from `archive/v1/tests/fixtures/` to `tests/fixtures/`.

### 2. Data model & SQLite

Schema (one DB per install, project-scoped tables):

- `projects(id, name, created_at, status)`
- `references(id, project_id, original_path, file_hash, phash, captured_at, gps_lat, gps_lon, width, height, uploader_member_id NULL, uploaded_at)`
- `stacks(id, project_id, picked_reference_id NULL, status)` — status: `pending|resolved|ignored`
- `stack_references(stack_id, reference_id)`
- `themes(id, project_id, name, color, order_index, ai_proposed)`
- `stack_themes(stack_id, theme_id)`
- `pages(id, theme_id, order_index, layout_id)`
- `page_items(id, page_id, kind, reference_id NULL, text_content NULL, slot_index, position_json)`
- `jobs(id, project_id, kind, status, started_at, finished_at, error)`
- Members/votes tables defined but unused in M1 (added in M2/M3).

Use plain SQL via `sqlite3` stdlib + a thin DAO module. No ORM — keeps schema visible and migrations explicit.

### 3. AI pipeline

- [ ] **Tier 1 (synchronous on upload)**: per file — SHA-256, EXIF (`captured_at`, GPS), perceptual hash (`imagehash.phash`), generate thumbnails (256w and 800w JPEG). Exact-dup detection via `file_hash`; near-dup via pHash Hamming distance ≤ 8.
- [ ] **Tier 2 (background job)**: a single `process_project` job:
  1. **Burst clustering**: same camera model + EXIF time-delta < 30s → candidate stack.
  2. **Visual clustering**: compute CLIP embeddings (cached on disk by file hash). For each burst candidate, confirm via cosine similarity. Also detect visually-similar shots across bursts that share a time window.
  3. **Theme proposal**: cluster stacks by (time-of-day partitions ≥ 6h apart) + GPS proximity + visual centroid. Name themes as `Theme 1..N` in M1; renaming is the user's job.
- [ ] Pick CLIP model: research `open_clip` model sizes; pick the smallest one that still does well on the vacation-20 fixture. Baseline candidates: `ViT-B/32` (fast, ~150MB) vs `ViT-L/14` (better, ~900MB). Decision recorded in `step-1-notes.md` after benchmarking.
- [ ] Job queue: in-process worker thread per project; jobs persisted to SQLite so restart resumes. No Celery.

### 4. Backend API

Resource-oriented, project-scoped, minimal:

- `GET /api/projects`
- `POST /api/projects` `{ name }`
- `GET /api/projects/{id}`
- `POST /api/projects/{id}/uploads` (multipart, batch)
- `POST /api/projects/{id}/process` → enqueues tier-2 job
- `GET /api/projects/{id}/jobs/{job_id}` → status/progress
- `GET /api/projects/{id}/stacks` `?status=pending|resolved|ignored`
- `PATCH /api/stacks/{id}` `{ picked_reference_id?, status? }`
- `GET /api/projects/{id}/themes`
- `POST /api/projects/{id}/themes` `{ name }`
- `PATCH /api/themes/{id}` `{ name?, order_index? }`
- `POST /api/themes/{id}/assign` `{ stack_id }`
- `GET /api/themes/{id}/pages`
- `POST /api/themes/{id}/pages`
- `PATCH /api/pages/{id}` `{ layout_id?, order_index? }`
- `POST /api/pages/{id}/items` `{ kind, reference_id?, text_content?, slot_index }`
- `PATCH /api/page_items/{id}` `{ position?, text_content? }`
- `DELETE /api/page_items/{id}`
- `POST /api/projects/{id}/book/auto-build`
- `POST /api/projects/{id}/export` → returns ZIP stream of `book.json` + `assets/`
- `GET /api/references/{id}/thumb` and `/medium` and `/original`

Total target: ~20 endpoints, all under one router file per resource.

### 5. JSON export schema (v1)

```json
{
  "schema_version": 1,
  "project": { "id": "...", "name": "...", "created_at": "..." },
  "themes": [
    {
      "id": "...",
      "name": "Beach day",
      "color": "#...",
      "order": 0,
      "pages": [
        {
          "id": "...",
          "order": 0,
          "layout_id": "grid-2x2",
          "items": [
            { "kind": "photo", "slot": 0, "asset": "assets/<hash>.jpg" },
            { "kind": "text", "slot": 1, "content": "Sunset at Tropea" }
          ]
        }
      ]
    }
  ],
  "assets": [
    { "path": "assets/<hash>.jpg", "sha256": "...", "captured_at": "...", "width": 4032, "height": 3024 }
  ]
}
```

Export bundle is a ZIP: `book.json` at the root + `assets/<hash>.jpg` for every referenced photo at full original resolution.

### 6. Frontend (Svelte + Vite)

- [ ] Mobile-first layout. Topbar with project name and three tabs (Stacks / Themes / Book). Hamburger menu for Project switch and Export.
- [ ] `Projects` view at `/` — list, create.
- [ ] `Project` view at `/p/<id>` — three sub-routes.
- [ ] `Stacks` view — list of stack cards (mobile); grid (desktop). Tap a stack → full-screen picker showing all photos in the stack. Tap a photo → confirm. Status filter chips (pending / resolved / ignored).
- [ ] `Themes` view — sections per theme (mobile, collapsible); columns (desktop). Stack chips draggable between sections; long-press to drag on mobile.
- [ ] `Book` view — theme picker; for the selected theme, a vertical list of pages (mobile) or row of page previews (desktop). One layout template in M1 (`grid-2x2`). Tap a slot to assign a photo from the theme's photo strip. Add text block via a button.
- [ ] Visual design: inherit color palette and typography from `archive/v1/frontend/styles/darkroom.css`. Use Svelte's scoped styles; one design token file.
- [ ] State: small Svelte stores per resource. Polling-based refresh every 5s while a job is running.

### 7. Tests

Written fresh per the test policy at the top of this step. Each test asserts a user-visible outcome through the v2 API or UI, not an internal field name.

- [ ] **Backend unit tests** (intent-level):
  - Given a known image, EXIF and capture-time are extracted correctly.
  - Given two near-identical images, the pipeline identifies them as duplicates.
  - Given a sequence of timestamps from one camera within seconds, they form a single burst stack.
  - Given a finished book, the exported JSON validates against the v2 schema.
- [ ] **Integration test** (one end-to-end story on the vacation-20 fixture):
  - Create project → upload 20 photos → process → expect stacks to exist → expect themes to exist → pick best per stack → assign each stack to a theme → auto-build book → export → the export ZIP contains every original at full resolution and a valid `book.json`.
  - Assertions are on counts and structure ("at least 1 theme," "every stack has a pick"), not on specific stack IDs, theme names, or response key spellings.
- [ ] **Playwright E2E** (one happy path, mobile viewport + desktop viewport):
  - User creates a project, uploads the fixture, taps "Process," waits for stacks to appear, picks a best shot in one stack, switches to Themes, drags a stack, switches to Book, auto-builds, exports.
  - Selectors use ARIA roles and accessible names (`getByRole('button', { name: 'Process new photos' })`), not CSS classes or IDs from v1.
- [ ] **Pre-push script** runs ruff + pytest + Playwright + (best-effort) trufflehog.

Anti-patterns the suite must avoid:
- Asserting on specific response key names that aren't part of the documented v2 API.
- Asserting on stack IDs or theme IDs being a particular shape.
- Asserting on UI text that is purely cosmetic (button labels are fine via accessible names; tooltip wording is not).
- Asserting on internal status strings (`provisional|final|needs_review`) — instead, assert on the *behavior* those statuses produce.

### 8. Tooling

- [ ] `uv sync` produces a working dev env.
- [ ] `npm install` + `npm run dev` produces a working frontend dev server.
- [ ] One command (`scripts/dev.sh`) runs FastAPI + Vite together.
- [ ] `ruff check .` and `pytest -q` both green.

## Non-goals reminder

If a feature feels great but is not on the M1 list, write it down in `step-2.md` (not yet created) and move on. M1's value is *one clean vertical slice* that we can iterate on.

## Decisions still open in M1

These need to be resolved early in the step:

1. **CLIP model size** — benchmark `ViT-B/32` vs `ViT-L/14` on the fixture. Pick highest quality that completes the 20-photo pipeline in <60s on the dev desktop. Decision recorded in commit message.
2. **Frontend folder layout** — `frontend/src/routes/`, `frontend/src/lib/api.ts`, `frontend/src/lib/stores/`. Confirmed when scaffolding.
3. **Page layout primitive** — a `position_json` of `{ x, y, w, h }` in 0..1 normalized space, plus an optional `crop` hint. Vendor decides actual pixels.

## How M1 is split into sub-steps

Implementation will land as a series of commits, each independently runnable:

- 1.1 — Repo scaffolding (`pyproject.toml`, `package.json`, dirs, fixture move).
- 1.2 — SQLite schema + DAO + tests.
- 1.3 — Backend: projects + uploads + tier-1 pipeline + thumbs.
- 1.4 — Backend: tier-2 pipeline (stacks + themes) + job queue.
- 1.5 — Backend: book CRUD + auto-build + export.
- 1.6 — Frontend: scaffold + projects screen.
- 1.7 — Frontend: stacks screen (mobile + desktop).
- 1.8 — Frontend: themes screen.
- 1.9 — Frontend: book screen + export.
- 1.10 — E2E tests + polish pass.

Each sub-step ends with a commit and a passing test suite. Sub-steps are reviewable as small, focused diffs.
