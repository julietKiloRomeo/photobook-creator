# Archive — v1 (pre-restart snapshot)

This directory contains the **complete prior implementation** of the photo book creator at the point of the v2 restart.

## Why it's here

The v1 implementation worked, but the implementation sprawl (30+ API endpoints, five-lens desktop-first UI, ad-hoc state) was no longer in line with the project vision:

- Multi-device, multi-user family curation on a local network.
- Mobile-first responsive UI organized around three concepts: **Stacks · Themes · Book**.
- Local-first AI pipeline (fast & cheap, deferred heavy work).
- Vendor-ready JSON export (Pixum / Mixbook downstream).

v2 will be rebuilt around those goals. This archive is kept verbatim for reference — algorithms, fixtures, UI design language, and lessons learned all live here.

## What's worth mining

- `photobook/clustering.py` — dedup, pHash, EXIF, CLIP-based clustering. Sound core; will be refactored behind a clearer pipeline interface in v2.
- `photobook/project_store.py` — SQLite layer. Schema will be reshaped for v2, but patterns are useful.
- `scripts/generate_vacation_fixture_pack.py` — fixture generator. Invaluable for v2 tests; will be moved back to top level when v2 needs it.
- `frontend/styles/darkroom.css` — visual design language (colors, typography, spacing). v2 will inherit the palette and feel.
- `tests/fixtures/vacation-20/` — 20 AI-generated vacation photos + manifest. Will be reused by v2 tests.

## What's intentionally being left behind

- `darkroom_v2.html` desktop-first five-lens shell.
- The granular per-resource REST API surface.
- The `PHOTOBOOK_DB_PATH` single-DB compatibility mode.
- Vanilla-JS frontend structure (v2 uses a framework — see top-level README).

## Status

**Frozen.** Do not edit files here. New work lands in the top-level v2 tree.
