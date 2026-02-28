# Photo Book Creator

Local-first tooling to build a photo book pipeline from ingestion through curation.

## Overview

Photo Book Creator is a local app that ingests photos, generates thumbnails for fast browsing, and prepares data for downstream clustering, deduplication, and layout. It keeps originals in place and stores derived assets + metadata locally.

## Requirements

- Python 3.10+
- Node 18+
- uv (Python package manager)

## Install

```bash
uv run --extra dev python -V
```

```bash
cd ui
npm install
```

## Run the API

```bash
uv run photobook-thumbnails --serve
```

API runs on `http://127.0.0.1:8000`.

## Run the UI

```bash
cd ui
npm run dev
```

The UI proxies `/api` to the local API server.

## Run Tests

```bash
uv run --extra dev pytest
```

## CLI Thumbnail Pipeline

Generate thumbnails and persist metadata in SQLite:

```bash
uv run photobook-thumbnails path/to/photos --cache-dir .cache/thumbnails --sizes 256 1024
```

## Repo Structure

- `src/photobook/`: backend modules (thumbnails, API, SQLite store)
- `tests/`: integration tests
- `ui/`: React/Vite UI
- `step-*.md`: project workflow steps
