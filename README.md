# shoebox

The family shoebox of photos — everyone reaches in, picks favorites, and builds a book together.

A calm, mobile-first, locally-hosted curation table where a family turns a pile of photos into a print-ready photo book. Deploys to `shoebox.valhalla` on the home LAN.

> **Status: M1 vertical slice complete (single-user).** A solo user can create a project, upload a folder of photos, auto-cluster into stacks and themes, build a draft book, and export structured JSON. Multi-user, voting, and the deploy story land in M2-M4. The previous v1 implementation is preserved verbatim under [`archive/v1/`](./archive/v1/) — see [`archive/v1/ARCHIVE_NOTES.md`](./archive/v1/ARCHIVE_NOTES.md) for what's worth mining.
>
> **Tests are not inherited from v1.** v1 tests asserted on v1 implementation details (endpoint paths, field names, DOM IDs) and would silently re-anchor v2 to v1's shape. v2 tests are written fresh against user intent — see the test policy in `step-1.md`.

## Quick start

Backend + frontend dev servers, with Vite proxying `/api` to FastAPI:

```bash
uv sync --extra dev
cd frontend && npm install && cd ..
./scripts/dev.sh
```

Then open <http://127.0.0.1:5173>.

## The three concepts

Everything in the product is built around three nouns:

1. **Stacks** — groups of visually similar shots. Pick the best per stack.
2. **Themes** — groups of stacks telling a story (e.g. "Beach day").
3. **Book** — pages per theme with photos and text in layouts.

Curation is durable: adding more photos later re-runs clustering but never
moves a stack you already filed. Reprocessing only proposes themes for
stacks that belong to no theme yet. Stacks move between themes by drag and
drop (pointer) or tap-then-pick (touch), and both themes and pages can be
deleted — deleting a theme returns its stacks to **Unassigned** rather
than discarding photos.

Duel (rapid 1:1 picking) and Timeline (chronological overview) are tools that serve the three concepts, not top-level navigation.

## Architecture (M1)

- **Backend**: FastAPI + SQLite (single DB at `data/shoebox.db`). Pillow + imagehash for the tier-1 ingest pipeline. Tier-2 clustering uses a pluggable Embedder interface — defaulting to a perceptual-hash embedder for fast/cheap M1, with OpenCLIP planned for M4 quality upgrade. Background work runs on a single in-process worker thread; jobs are mirrored to SQLite.
- **Frontend**: Svelte + Vite + TypeScript. Mobile-first responsive. Hash routing. ~20 kB gzipped bundle.
- **Storage**: full-resolution originals plus multi-tier derivatives under `data/projects/<id>/{originals,thumbs,medium}`.
- **Export**: ZIP with `book.json` (schema_version=1) + `assets/<sha256>.<ext>` originals.
- **Logging**: stderr plus a rotating file at `data/logs/shoebox.log`. Upload rejections, job failures and unhandled request errors are all logged with their underlying cause. The HTTP response keeps only a coarse rejection reason, because decoder errors can echo raw file bytes back to the client. Tune with `SHOEBOX_LOG_LEVEL` (default `INFO`) and `SHOEBOX_LOG_TO_FILE`.

### Why was my photo skipped?

Check `data/logs/shoebox.log` — each rejection is logged with the filename
and the concrete cause. Extensions are matched case-insensitively, so
`.jpg`, `.JPG`, `.jpeg` and `.JPEG` are all accepted. Files truncated by a
phone or a sync client are decoded as far as they go rather than dropped,
and unreadable EXIF costs the photo its timestamp, not its place in the
project.

## Decisions locked in

- Backend: FastAPI + SQLite.
- Frontend: Svelte + Vite, mobile-first responsive.
- AI: three-tier pipeline — instant cheap (hash/EXIF/pHash) on upload, deferred heavy on owner action, optional cloud for theme names later.
- Identity: per-device cookie. First visit asks name + color. No accounts. **(M2)**
- Roles: owner / curator / contributor / viewer. **(M2)**
- Votes: automatic majority pick; owner can override. **(M3)**
- Concurrency: last-write-wins with live refresh.
- Storage: full-res originals on disk + multi-tier derivatives.
- Export: JSON + `assets/` folder, vendor-agnostic.
- Deploy target: Docker on `valhalla` behind Traefik. **(M4)**

## Local checks

```bash
# Backend
uv run pytest -q
uv run ruff check .

# Frontend
cd frontend && npm run check && npm run build

# End-to-end (Playwright)
cd frontend && npx playwright test
```

## Milestones

- **M1** — Vertical slice MVP (single-user, polished): project → upload → process → stacks → themes → book → export. **✅ Complete.**
- **M2** — Multi-user: join-by-link, identity, roles, presence.
- **M3** — Voting and Duel mode.
- **M4** — Polish, Timeline lens, more layouts, deploy to `shoebox.valhalla` via Docker + Traefik. Real OpenCLIP embedder benchmarked on valhalla hardware.
- **M5** — Vendor export helpers (Pixum / Mixbook converters, PDF preview).

See `AGENTS.md` for agent workflow and `step-1.md` for the active step.
