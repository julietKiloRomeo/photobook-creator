# Photo Book Creator (v2)

A calm, mobile-first, locally-hosted curation table where a family turns a pile of photos into a print-ready photo book together.

> **Status: restart in progress.** The previous implementation is preserved verbatim under [`archive/v1/`](./archive/v1/). v2 is being rebuilt from scratch around a sharper product vision. See `step-1.md` for the active milestone.

## Vision

- **Audience**: non-technical family members — parents, kids, grandparents.
- **Deployment**: owner's laptop in dev, a small box (`valhalla` mini-PC) on the LAN for staging. Travel router provides network only.
- **Devices**: phones for contributors, laptop for the owner.
- **Output**: structured JSON handoff — convertible later to Pixum / Mixbook formats.

## The three concepts

Everything in the product is built around three nouns:

1. **Stacks** — groups of visually similar shots. Pick the best per stack.
2. **Themes** — groups of stacks telling a story (e.g. "Beach day").
3. **Book** — pages per theme with photos and text in layouts.

Duel (rapid 1:1 picking) and Timeline (chronological overview) are demoted from top-level navigation to tools that serve the three concepts.

## Decisions locked in

- Backend: **FastAPI + SQLite**.
- Frontend: **Svelte + Vite**, mobile-first responsive.
- AI: three-tier pipeline — instant cheap (hash/EXIF/pHash) on upload, deferred heavy (visual clustering, theme proposals) on owner action, optional cloud (nicer theme names). Best viable local model quality.
- Identity: per-device cookie. First visit asks name + color. No accounts.
- Roles: owner / curator / contributor / viewer.
- Votes: automatic majority pick; owner can override.
- Concurrency: last-write-wins with live refresh.
- Storage: full-res originals on disk + multi-tier derivatives.
- Export: JSON + `assets/` folder, vendor-agnostic.
- Deploy target: Docker on `valhalla` behind Traefik.

## Milestones

- **M1** — Vertical slice MVP (single-user, polished): project → upload → process → stacks → themes → book → export.
- **M2** — Multi-user: join-by-link, identity, roles, presence.
- **M3** — Voting and Duel mode.
- **M4** — Polish, Timeline lens, more layouts, deploy to `valhalla` via Docker + Traefik.
- **M5** — Vendor export helpers (Pixum / Mixbook converters, PDF preview).

See `AGENTS.md` for agent workflow and `step-1.md` (forthcoming) for the active step.
