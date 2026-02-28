# Photo Book Creator - Architecture Plan

This plan breaks the app into small, testable modules. Each module has a single job, clear inputs/outputs, and minimal side effects.

## 1) Project + Storage

**Goal:** Keep a durable, queryable record of everything without moving originals.

- Module: `project_store`
  - Stores project metadata and processing state.
  - Backed by SQLite.
  - Keeps absolute file paths only; never copies originals.

**Core tables (SQLite):**
- `projects`: id, name, created_at
- `sources`: id, project_id, type (folder|file|url), path_or_url, added_at
- `photos`: id, project_id, source_id, path, sha256, mime, width, height, taken_at, gps_lat, gps_lon
- `thumbnails`: photo_id, size, path
- `clusters`: id, project_id, name, start_at, end_at, kind (event|theme)
- `cluster_photos`: cluster_id, photo_id, rank, role (member|best)
- `duplicate_groups`: id, project_id
- `duplicate_photos`: group_id, photo_id, distance, is_best
- `pages`: id, project_id, chapter_id, page_index
- `page_items`: id, page_id, item_type (photo|text), photo_id, text, x, y, w, h, z

**Testability:**
- Unit tests for schema migration and basic CRUD.

## 2) Intake + Indexing

**Goal:** Accept folders, files, and URLs; index them into SQLite.

- Module: `ingest`
  - Input: list of paths/urls
  - Output: rows in `sources` + `photos`
  - Behavior: reads metadata using exiftool, hashes files (sha256), detects duplicates by hash
  - URL handling: download to a project cache folder and track as source

**Testability:**
- Given a small fixture folder, it should create the expected rows.

## 3) Thumbnails

**Goal:** Provide fast UI rendering without loading originals.

- Module: `thumbnails`
  - Input: photo paths
  - Output: thumbnail files + `thumbnails` table rows
  - Uses ImageMagick or Pillow
  - Sizes: 256px and 1024px (configurable)

**Testability:**
- Ensure thumbnails exist and dimensions match expected size.

## 4) Clustering (Events)

**Goal:** Group photos by time and location across all sources.

- Module: `cluster_events`
  - Input: photos with timestamps and optional GPS
  - Output: `clusters` rows + `cluster_photos` relations
  - Method: time window clustering; refine by GPS distance if available
  - Config: time window range (e.g., 30-120 minutes)

**Testability:**
- With fixture photos, verify expected cluster counts and time ranges.

## 5) Duplicate Stacking

**Goal:** Detect near-duplicates and suggest best shots.

- Module: `dedupe`
  - Input: thumbnails or reduced images
  - Output: `duplicate_groups` + `duplicate_photos`
  - Method: perceptual hash + Hamming distance
  - Thresholds configurable by project

**Testability:**
- Known duplicate set should land in the same group.

## 6) Aesthetic Scoring

**Goal:** Rank photos without LLMs using model-based scoring.

- Module: `aesthetic_score`
  - Input: thumbnails
  - Output: score per photo (stored in `photos` or new `photo_scores` table)
  - Model: LAION aesthetic predictor or NIMA
  - Optional heuristics: blur, exposure, faces
  - GPU optional, CPU fallback supported

**Testability:**
- Scores should be stable for the same input; model load tests.

## 7) Chapter/Themes

**Goal:** Turn clusters into chapters and allow manual theme creation.

- Module: `chapters`
  - Input: event clusters
  - Output: chapter records + ordering
  - Supports manual creation and renaming

**Testability:**
- Create, reorder, and rename chapters.

## 8) Staging + Page Layout

**Goal:** Allow users to assemble pages with photo + text items.

- Module: `layout`
  - Input: selected photos + page counts
  - Output: `pages` + `page_items`
  - Supports drag-drop and reuse of photos across chapters

**Testability:**
- Add/remove/reorder page items; verify persistence.

## 9) Preview + Export

**Goal:** Provide a readable book preview and optional export.

- Module: `export`
  - Output: JSON/YAML listing photos + texts per page
  - Optional: copy selected photos to an export folder

**Testability:**
- Export format matches schema and references valid photo paths.

## 10) UI + API

**Goal:** A local web app with a small backend.

- UI: React/Vite
- Backend: FastAPI (Python)
  - Serves project state and thumbnails
  - Runs background jobs with progress

**Testability:**
- API integration tests for key endpoints.

## 11) Background Jobs

**Goal:** Long tasks run asynchronously with progress updates.

- Module: `jobs`
  - Queue: simple in-process worker initially
  - Jobs: ingest, thumbnails, cluster, dedupe, scoring
  - Progress stored in SQLite

**Testability:**
- Start/stop jobs and resume after restart.

## 12) Optional Agent Runner

**Goal:** Allow backend to call `opencode run` to label themes.

- Module: `agent_runner`
  - Input: cluster summaries
  - Output: suggested names/tags
  - Runs as a background job; outputs stored in DB

**Testability:**
- Mocked process runner returns canned labels.

## Integration Flow

1) Create project
2) Ingest sources and index photos
3) Generate thumbnails
4) Cluster into events
5) Detect duplicate stacks
6) Score aesthetics
7) Create chapters from clusters
8) Manual curation in UI (staging + pages)
9) Preview and export

## Early Milestones

**Milestone 1:** Ingest + thumbnails + basic UI grid
**Milestone 2:** Event clustering + duplicate stacks
**Milestone 3:** Aesthetic scoring + best shot suggestions
**Milestone 4:** Chapters/pages UI + export
