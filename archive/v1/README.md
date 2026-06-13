# Photo Book Creator (Restart)

This branch is a clean restart.

- Frontend includes a projects front page (`index.html`) and darkroom editor (`darkroom_v2.html`).
- Persistent storage: SQLite + per-project file storage under `.photobook-data/projects/<project-id>/`.
- Agent setup is kept in `AGENTS.md`, `.agents/`, and `.codex/`.
- Darkroom UI assets are split into `frontend/styles/darkroom.css` and `frontend/js/*`.

## Product Direction

The workflow remains:

1. Intake references (paths/URIs + metadata)
2. Organize into chapters and pages
3. Place photo/text items on pages
4. Export structured JSON

## Requirements

- Python 3.10+
- `uv`

## Install

```bash
uv sync --extra dev
```

For full-quality clustering (imagededup + OpenCLIP), install ML extras:

```bash
uv sync --extra dev --extra ml
```

Generate the vacation fixture pack (20 AI images + manifest) via OpenAI image generation using llm-gateway credentials from `~/.codex/config.toml` (`model_providers.topsoe`):

```bash
uv run scripts/generate_vacation_fixture_pack.py
```

Optional overrides:

```bash
uv run scripts/generate_vacation_fixture_pack.py --model gpt-image-1.5 --size 1024x1024 --quality low
```

## Run API + UI

```bash
uv run photobook-api --host 127.0.0.1 --port 8000
```

- `GET /` serves the projects front page.
- `GET /darkroom/{project_id}` serves the darkroom editor for a project.
- Default data root: `.photobook-data/`
- Compatibility mode: set `PHOTOBOOK_DB_PATH=/path/to/project.db` for single-project direct DB mode.

## API

- `GET /api/health`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `POST /api/projects/{project_id}/uploads`
- `GET /api/projects/{project_id}/uploads`
- `GET /api/projects/{project_id}/references/{reference_id}/image`
- `POST /api/projects/{project_id}/process`
- `GET /api/projects/{project_id}/duplicates`
- `POST /api/projects/{project_id}/reset`
- `POST /api/projects/{project_id}/stacks/{stack_id}/split`
- `GET /api/intake/references`
- `POST /api/intake/references`
- `GET /api/stacks`
- `POST /api/duel/pick`
- `GET /api/themes`
- `POST /api/themes`
- `PATCH /api/themes/{theme_id}`
- `POST /api/themes/assign`
- `GET /api/timeline`
- `GET /api/chapters`
- `POST /api/chapters`
- `PATCH /api/chapters/{chapter_id}`
- `POST /api/chapters/reorder`
- `GET /api/chapters/{chapter_id}/pages`
- `POST /api/chapters/{chapter_id}/pages`
- `GET /api/pages/{page_id}/items`
- `POST /api/pages/{page_id}/items`
- `PATCH /api/pages/items/{item_id}`
- `POST /api/book/auto-build`
- `POST /api/export`

## Local Checks

Required backend checks:

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest -q
```

Strict backend integration gate:

```bash
uv run --extra dev pytest -m gate -q
```

## Gate Suite (Playwright)

Run the strict gate suite locally when Playwright files are present (`package.json`, `playwright.config.*`, and `tests/e2e` or `e2e`):

```bash
npm ci
npx playwright install --with-deps
npx playwright test
```

## CI Behavior

GitHub Actions defines two lanes:

1. **Backend checks (required):** `uv sync --extra dev`, `ruff`, and `pytest`.
2. **Full-app gate suite (non-blocking):** runs Playwright if present and is marked `continue-on-error: true`.

If the gate lane fails, CI uploads Playwright artifacts (`playwright-report`, `test-results`) for debugging, but it does not block merging.
