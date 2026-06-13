# Step 2 — Manual Test Pass + M2 Multi-User

**Goal of this step**:
1. **First**, a human (you) drives the M1 vertical slice in a real browser to confirm it actually feels right — automated tests passed, but no eyes have seen the UI yet.
2. **Then**, based on what's learned, start M2 (multi-user / join-by-link / identity / roles / presence).

This file is the handoff for a fresh session. Read this top-to-bottom and you'll have full context without rereading the whole conversation.

---

## Where we left off

- M1 vertical slice is **code-complete and all-green** (see `step-1.md` marked "(Completed)").
- 37 backend pytest tests, ruff clean, svelte-check clean, 2 Playwright tests (desktop Chromium + Pixel 5 mobile) all pass.
- Bundle: 51 kB JS / 20 kB CSS uncompressed.
- Git log on `main` ends at `73572e9 Sub-step 1.10: E2E test + polish; mark step-1 complete`.
- v1 implementation is archived verbatim under `archive/v1/`. v1 tests are NOT inherited (see test policy in `step-1.md` and the archive notes).

**What has not happened yet**: a human has not opened the app in a browser. The Playwright E2E covers the happy path mechanically, but no real eyes have judged the calm/feel/aesthetic. That's the first task in this step.

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

- [ ] _(blocker / annoyance / polish)_ ...

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

- **2.0** — Manual test pass (this file's checklist above). Outcomes captured under "Manual-test findings". (You drive; no code unless something breaks.)
- **2.1** — Address any blocker/annoyance findings from 2.0.
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
| `uv run pytest -q` | Backend test suite (37 tests, ~10s) |
| `uv run ruff check .` | Lint |
| `cd frontend && npm run check` | svelte-check (TS/Svelte types) |
| `cd frontend && npm run build` | Production frontend build (`dist/`) |
| `cd frontend && npx playwright test` | E2E (desktop + mobile Chromium) |
| `git log --oneline -20` | Where we are on `main` |
