# Step 2 — Manual Test Pass + M2 Multi-User

**Goal of this step**:
1. **First**, a human (you) drives the M1 vertical slice in a real browser to confirm it actually feels right — automated tests passed, but no eyes have seen the UI yet.
2. **Then**, based on what's learned, start M2 (multi-user / join-by-link / identity / roles / presence).

This file is the handoff for a fresh session. Read this top-to-bottom and you'll have full context without rereading the whole conversation.

---

## Where we left off

*The state below is from when this file was first written, at the start
of step-2. For the current state (after sub-step 2.1), jump to
"Where to resume" below.*

- M1 vertical slice is **code-complete and all-green** (see `step-1.md` marked "(Completed)").
- 37 backend pytest tests, ruff clean, svelte-check clean, 2 Playwright tests (desktop Chromium + Pixel 5 mobile) all pass.
- Bundle: 51 kB JS / 20 kB CSS uncompressed.
- Git log on `main` ends at `73572e9 Sub-step 1.10: E2E test + polish; mark step-1 complete`.
- v1 implementation is archived verbatim under `archive/v1/`. v1 tests are NOT inherited (see test policy in `step-1.md` and the archive notes).

**What had not happened yet at the time**: a human had not opened the app in a browser. The Playwright E2E covers the happy path mechanically, but no real eyes have judged the calm/feel/aesthetic. That was the first task in this step — sub-step 2.0, now done.

---

## Where to resume (read this first in a fresh session)

`step-2.md` is the umbrella for sub-steps 2.0 → 2.8. So far:

- **2.0 Manual test pass** — done (jkr drove it, 8 findings logged below).
- **2.1 Wave A bug fixes** — done. B-1/B-2/B-3 fixed and committed
  (`e80e158`). Full record + self-critique deferrals are in
  `step-2.1.md`.
- **Everything else** — pending.

`git log --oneline` ends at:

```
e80e158 Sub-step 2.1: Wave A bug fixes (B-1 themes, B-2 text blocks, B-3 export)
8373512 Add step-2.md: manual test gate + M2 multi-user plan
73572e9 Sub-step 1.10: E2E test + polish; mark step-1 complete
```

Not pushed yet. Branch is ahead of `origin/main` by 12 commits.

### Two work streams compete for the next sub-step

1. **Sub-step 2.1.b — Wave B (manual-test findings F-/R-/P-)**.
   Brainstorming pass first (see `brainstorming` superpower skill), then
   code. Items: F-1 folder uploads, F-2 HEIC and other formats, F-3
   drag-drop stacks between themes, R-1 remove the explicit Process
   button, P-1 overall UX redesign, P-2 book builder mental model.
   Best done before more multi-user code lands, because each touches UI
   surfaces M2 also touches (upload toolbar, themes, book).
2. **Sub-step 2.2 — M2 auth scaffolding**. The plan below (`SHOEBOX_SECRET_KEY`,
   signed cookies, schema additions, etc.) is unchanged from when this
   file was first written. No work has started.

ox-47's recommendation: **do 2.1.b first** — running a brainstorming
pass with jkr while the UX context is fresh is cheaper than retrofitting
multi-user changes later. But this is jkr's call.

### Deferred technical items captured in `step-2.1.md` self-critique

These are NOT in the F-/R-/P- list above; they came out of ox-47's
self-review and belong to later milestones:

- **M3 candidate**: reprocessing wipes stack→user-theme assignments via
  the `replace_stacks` cascade. The user theme entity survives, but its
  stack memberships do not. `dao.replace_stacks` already calls this out
  as M3 work. File an issue when the M3 milestone opens.
- **Polish** (any time): theme name dedup (no UNIQUE on `(project_id, name)`),
  hardcoded `slot_index = 100` magic number in `BookScreen.svelte`, two
  dead CSS rules around `.remove` in `BookScreen.svelte:425-426`,
  `themePhotos()` not strictly reactive within a single picker open.

### Environment caveats picked up during 2.1

- **Trufflehog scan can't run via podman on this host**: btrfs root +
  overlay storage driver mismatch. Sub-step 2.1 was committed with a
  manual diff-grep instead. Pre-commit secrets scan needs either a
  podman storage-driver fix (`~/.config/containers/storage.conf` →
  `driver = "vfs"`) or a native trufflehog install before the next
  commit. AGENTS.md still mandates the scan.
- **ox-47's audit stack on :8001 / :5174** may still be running from
  the 2.1 Playwright run. Safe to leave or kill. `data-audit/` is
  untracked and not in `.gitignore`; either add to gitignore or delete
  the directory when the audit backend is stopped.
- **Playwright env-var escape hatches** (`SHOEBOX_E2E_BASE_URL`,
  `VITE_API_TARGET`) were added in 2.1 and proved useful — keep them
  in mind when running E2E against a non-default port.

---

## How to bring the dev environment back up

From the repo root:

```bash
# One-time, if dependencies aren't installed yet
uv sync --extra dev
cd frontend && npm install && cd ..

# Start both servers (backend on :8000, frontend on :5173, /api proxied)
./scripts/dev.sh
```

Then open **<http://localhost:5173>** (or `http://127.0.0.1:5173` if IPv6 is being weird).

To stop: `Ctrl-C` in the terminal running `dev.sh`, or `pkill -f shoebox-api`.

If you want the dev server reachable from another device on your LAN (e.g., to try the mobile UI on an actual phone), pass `--host`:

```bash
# Backend
uv run shoebox-api --host 0.0.0.0 --port 8000 --reload
# Frontend (separate terminal)
cd frontend && npm run dev -- --host 0.0.0.0
```

Caveat: the dev proxy in `frontend/vite.config.ts` points `/api` at `127.0.0.1:8000`. For LAN testing you'd build (`npm run build`) and let FastAPI serve the static `dist/` instead — not wired in M1, would be a small M2 task if you want phone-on-LAN testing now.

---

## Manual test checklist (do this first)

A fresh session should walk through this list before touching M2 code. Each item is a single user-visible outcome to confirm.

### Projects screen (`/`)

- [ ] Page loads with the heading "Your shoeboxes" and a calm one-line tagline.
- [ ] Typography is readable, spacing is generous, nothing feels cramped.
- [ ] On mobile viewport (DevTools responsive mode, narrow): no horizontal scroll, layout still pleasant.
- [ ] Create form: typing a name enables the Create button; submitting navigates to `/p/<id>`.
- [ ] Listing shows projects with name + creation date.
- [ ] Refresh button (⟳) reloads without a flash.
- [ ] Delete shows a confirm dialog and works.

### Project shell

- [ ] Top bar shows `shoebox` brand + the project name + Stacks/Themes/Book tab segmented control.
- [ ] Clicking the brand returns to projects list.
- [ ] On narrow viewports the tabs shrink gracefully.
- [ ] URL hash updates as you switch tabs (`#/p/<id>/stacks` etc.); back/forward work.

### Upload + process toolbar

- [ ] "Upload photos" opens a native file picker.
- [ ] After picking, the button label cycles to "Uploading…" and back, and the "Added N · M duplicates" summary appears.
- [ ] Uploading the same files again shows duplicates = N, accepted = 0.
- [ ] "Process new photos" cycles to "Processing… X%" with live status updates from the backend.
- [ ] When done, the label returns to "Process new photos" and the child screens refresh.

### Stacks screen

- [ ] After processing 8–20 fixture photos, the Pending filter may be empty (fixture has no EXIF, every stack auto-resolves). The empty-state hint should offer a one-click switch to "All".
- [ ] All filter shows thumbnail cards in a responsive grid.
- [ ] Cards show: thumbnail, status pill (resolved/pending/ignored), and a count badge when the stack has >1 photo.
- [ ] Tapping a card opens a full-screen picker on phone, an inset modal on desktop.
- [ ] In the picker: tapping a photo marks it "Picked" with the accent badge and resolves the stack.
- [ ] "Ignore stack" works and the modal closes.

### Themes screen

- [ ] At least one theme exists after processing (auto-proposed, named "Day 1" by default for no-EXIF fixtures).
- [ ] "Add theme" inline form works.
- [ ] "Rename" prompt works and persists after refresh.
- [ ] Tapping a stack chip selects it (accent border); a "Move selected stack here" button appears on each theme card.
- [ ] Tapping that button moves the stack and the assignment updates immediately.
- [ ] Tap-deselect works (tapping the same selected chip again).

### Book screen

- [ ] Theme picker chips at the top scroll horizontally on narrow screens.
- [ ] "Auto-build draft" populates pages with 4-slot 2×2 grids of photos.
- [ ] Tapping a slot opens the photo picker scoped to that theme.
- [ ] Tapping a picker photo fills the slot.
- [ ] "+ Text" adds a text block via prompt; ✕ removes an item.
- [ ] "+ Add page" creates an empty page at the end.
- [ ] "Export JSON ↓" downloads a real ZIP file. Open it: contains `book.json` + `assets/<sha256>.jpg` at full resolution.

### General feel

- [ ] Motion is calm — no bouncy animations, no flashy transitions.
- [ ] Colours match the calm palette (cream/off-white surfaces, muted purple accent, soft borders).
- [ ] Errors (if any) surface inline in their context, not as alerts.
- [ ] Nothing important is hidden behind hover — usable with touch.

### Bugs / annoyances to capture

When you find anything that's off, add it under the **Manual-test findings** section below (further down in this file). Each finding gets a checkbox so we can knock them out before M2.

---

## Manual-test findings

(Populate this as you go. Format: severity tag + short description.)

Captured from jkr's first pass on <http://127.0.0.1:5173/>:

### Upload + processing
- [ ] _(feature)_ **F-1** Upload must accept folders and traverse them recursively (drag-and-drop of a folder; `<input webkitdirectory>`).
- [ ] _(feature)_ **F-2** Upload must accept many file formats. Currently HEIC fails on upload. Minimum: JPEG, PNG, HEIC/HEIF, WebP, GIF, TIFF; ideally also raw (CR2/NEF/ARW/DNG) deferred to a later milestone but rejected with a clear message, not a crash.
- [ ] _(redesign)_ **R-1** Remove the separate "Process new photos" button. Processing is implied by upload. There is no user-facing reason to upload without processing. Backend can still run processing as a background task; the UI just shows progress inline with upload.
- [ ] _(polish)_ **P-1** Overall UX feels generic. Wants a smoother, more deliberate flow — to be specified in a follow-up brainstorm pass before redesign.

### Themes
- [x] _(blocker)_ **B-1** A theme added *before* uploading photos disappears after the first upload+process cycle. Either auto-proposal is wiping user-created themes, or the user theme was created against a different project/session. Needs a regression test: "theme created pre-upload survives upload+process". *Fixed in sub-step 2.1: pipeline now only deletes `ai_proposed` themes; user mutations on an auto theme implicitly adopt it. Regression tests: `test_user_created_theme_survives_processing`, `test_renamed_auto_theme_survives_reprocessing`.*
- [ ] _(feature)_ **F-3** Drag-and-drop of stacks (or individual photos) from one theme to another. Today only the "select stack chip + Move selected stack here button" path works, which is clunky.

### Book builder
- [x] _(blocker)_ **B-2** "+ Text" appears to be off-by-one: after submitting the first text block nothing visible happens; submitting a second text block makes the *first* one appear. Likely a stale-state / missing reactive update after the prompt resolves, or a write to the previous index. Needs a regression test: "adding two text blocks in sequence shows both in order". *Fixed in sub-step 2.1: text blocks render in a dedicated `<ul>` with reactive Svelte declarations split from the 2x2 photo grid. Regression test: `frontend/e2e/regression-book-text.spec.ts`.*
- [x] _(blocker)_ **B-3** "Export JSON ↓" returns **HTTP 405 Method Not Allowed**. Needs a regression test: "export endpoint returns a ZIP for a valid project". *Fixed in sub-step 2.1: export route accepts GET (idempotent read) in addition to POST. Regression test: `test_export_endpoint_supports_get_for_native_download_link`.*
- [ ] _(polish)_ **P-2** The book builder mental model is not obvious to a first-time user (jkr couldn't tell what was supposed to happen). Needs UX work after B-2 is fixed; possibly an empty-state hint or a brief inline guide.

### Cross-cutting
- [ ] _(policy)_ Every item above with a B-/F-/R- tag must ship with an intent-level regression test (backend pytest where the bug is server-side; Playwright where the bug is purely UI) so jkr does not see the same issue twice.

---

## Decisions still locked in (carried from step-1.md)

- Backend: FastAPI + SQLite.
- Frontend: Svelte + Vite + TypeScript, mobile-first responsive.
- AI: three-tier pipeline. M1 ships with the cheap `PhashEmbedder` default; M4 swaps in OpenCLIP after benchmarking on `valhalla`.
- Identity: per-device cookie, name + colour, no accounts.
- Roles: owner / curator / contributor / viewer.
- Voting: automatic majority pick, owner can override.
- Concurrency: last-write-wins with live refresh.
- Storage: full-resolution originals + thumb/medium derivatives.
- Export: JSON ZIP, vendor-agnostic.
- Deploy: Docker behind Traefik at `shoebox.valhalla` (M4).
- Test policy: assert intent only; never adopt v1 tests; never assert on internal field names or status strings (see `step-1.md` test policy).

---

## M2 — Multi-User (after manual test passes)

Goal: contributors join a project via link/QR, identify themselves with a name + colour, and the API enforces role-based permissions.

### Scope (in)

- **Identity**: first visit on a device asks for name + colour. Stored in a signed cookie keyed per project. No password, no account table.
- **Join flow**: project owner generates a share link; visitors land on a join screen, fill name + colour, then drop into the project with their role.
- **Roles** (enforced server-side):
  - **Owner**: everything. The creator of a project is automatically the owner.
  - **Curator**: edit stacks/themes/pages; cannot manage members or export.
  - **Contributor**: upload, mark favourites; cannot edit themes or pages.
  - **Viewer**: read-only.
- **Members panel**: owner can see all members, change roles, kick.
- **Share modal**: shows the join link + a QR code; lets the owner pick the default role for new joiners.
- **Presence**: avatar dots in the top bar showing who else is currently in the project. Polling-based heartbeat (no WebSocket in M2).

### Scope (out — still later)

- Voting + Duel mode (M3).
- Timeline lens (M4).
- Docker / Traefik deploy (M4).
- OpenCLIP swap (M4).
- Vendor converters (M5).

### Data model deltas

The `members` and `votes` tables already exist in the M1 schema. Additions needed:

- `projects` gains a `default_join_role` (string).
- `projects` gains a `share_token` (random, opaque) — used in the join URL so the share link can be rotated without changing the project id.
- `members` gains a `device_token` (random per device) so the server can re-identify a device on subsequent visits.
- New `presence` table or in-memory map keyed by `(project_id, member_id)` with a `last_seen_at`.

### API additions (M2)

- `POST /api/projects/{id}/share/rotate` → owner generates a fresh share token.
- `GET /api/join/{share_token}` → public; returns project name + default role for the join screen.
- `POST /api/join/{share_token}` `{ name, colour }` → creates a `Member` with `device_token`; sets a signed cookie; returns the member.
- `GET /api/projects/{id}/me` → returns the current member (if any) for the cookie+project.
- `GET /api/projects/{id}/members` → owner-only.
- `PATCH /api/members/{id}` → owner can change role.
- `DELETE /api/members/{id}` → owner can kick.
- `POST /api/projects/{id}/presence/heartbeat` → updates `last_seen_at`; returns the list of active members.
- All existing endpoints gain role checks via a dependency.

### Frontend additions

- Cookie + identity bootstrap on app load.
- `/join/<share_token>` route with the name + colour form.
- "Share" button in the top bar opens a modal with link + QR (use `qrcode-svg` or generate inline).
- Avatar cluster in the top bar showing presence.
- Members panel (owner-only) under a menu in the top bar.
- API-level role error toasts: if a contributor tries to rename a theme, show a friendly "Curators and owners can do that" message rather than a 403 dump.

### Test plan (M2)

- Backend: a contributor cannot rename a theme (403). An owner can. A kicked member's cookie no longer authenticates.
- Backend: cookie + device token roundtrips correctly across requests.
- Backend: share-token rotation invalidates old links.
- E2E (Playwright): owner creates a project → opens Share → copies link → second browser context visits the link → fills name + colour → lands in the project → can upload → cannot edit themes (button absent or disabled with explainer).

### Open questions to resolve early in M2

1. **Cookie signing**: stdlib `itsdangerous`? Or FastAPI's built-in? Lean toward `itsdangerous` for explicitness.
2. **QR code**: server-rendered SVG (no frontend dep) vs. tiny client-side library. Lean server-side.
3. **Presence cleanup**: how long after `last_seen_at` does a member fall off the avatar cluster? 30 s probably.
4. **Project-level vs. instance-level secret**: a single `SHOEBOX_SECRET_KEY` env var for cookie signing? Generate on first boot, persist to `data/secret.key`?

---

## Sub-step plan for step-2

The manual test gate goes first; everything else is contingent on it.

- **2.0** — Manual test pass (this file's checklist above). Outcomes captured under "Manual-test findings". (You drive; no code unless something breaks.) **(Completed)** — jkr drove the pass; 8 findings captured (B-1/2/3, F-1/2/3, R-1, P-1/2).
- **2.1** — Address any blocker/annoyance findings from 2.0. **(Completed — Wave A only)** — B-1, B-2, B-3 fixed in commit `e80e158`. Self-critique log + deferrals live in `step-2.1.md`. Wave B (F-/R-/P-) deferred to 2.1.b (see "Where to resume" below).
- **2.1.b** — *(new, not started)* Wave B: F-1 folder uploads, F-2 broader file format support (HEIC etc.), F-3 drag-drop stacks between themes, R-1 remove the explicit "Process new photos" button, P-1 overall UX brainstorm, P-2 book builder mental model. Per the original manual-test triage, a brainstorming pass should happen before code (`brainstorming` superpower skill is available).
- **2.2** — Auth scaffolding: `SHOEBOX_SECRET_KEY` plumbing, signed-cookie helper, `members` + `presence` schema additions, `share_token` and `default_join_role` on `projects`.
- **2.3** — Join flow: `/api/join/...` endpoints + `/join/<token>` frontend route. Owner auto-created on project creation.
- **2.4** — Role enforcement: dependency on every mutating endpoint, with intent tests for each role boundary.
- **2.5** — Share modal + QR.
- **2.6** — Members panel.
- **2.7** — Presence heartbeat + avatar cluster.
- **2.8** — Polish + E2E covering the two-browser join scenario.

Each sub-step ends with a focused commit and a passing test suite.

---

## Quick reference

| Command | What it does |
| --- | --- |
| `./scripts/dev.sh` | Backend + frontend dev servers with `/api` proxied |
| `uv run pytest -q` | Backend test suite (41 tests after sub-step 2.1, ~10s) |
| `uv run ruff check .` | Lint |
| `cd frontend && npm run check` | svelte-check (TS/Svelte types) |
| `cd frontend && npm run build` | Production frontend build (`dist/`) |
| `cd frontend && npx playwright test` | E2E (desktop + mobile Chromium) |
| `git log --oneline -20` | Where we are on `main` |
