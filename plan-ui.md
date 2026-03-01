# UI Plan - Intermediate Stage (No Scroll)

## Goal
- Provide a single-screen, responsive UI that fits all key actions without scrolling.
- Organize workflow into stage tabs and keep a persistent global progress banner.
- Always show feedback for slow background jobs.

## Layout Overview
- App shell with three zones: header, main stage panel, status rail.
- Header contains project name, stage tabs, and a global progress banner.
- Main panel shows exactly one stage at a time (no scroll).
- Status rail shows job queue, last run summaries, and system health.

## Structure
- Header
  - Project name
  - Global progress banner (running job + percent)
  - Stage tabs (Radix Tabs): Intake, Thumbnails, Clusters, Duplicates
- Main panel
  - Stage-specific content (fixed height cards)
- Status rail
  - Jobs list (queued, running, completed)
  - Recent outcomes (last run timestamps, counts)

## Stage Content
- Intake
  - Dropzone
  - Add buttons (folder/file/URL)
  - Compact source list (limit 6) with +N more
- Thumbnails
  - Thumbnail grid preview (limit 8-12)
  - Status card with progress and cache info
- Clusters
  - Cluster cards (limit 6)
  - Summary panel (cluster count + time ranges)
- Duplicates
  - Stack list (limit 6)
  - Selected stack preview (2-4 tiles), best-shot badge

## Global Progress Banner
- Always visible in the header.
- Shows job name, stage, progress bar, and counts.
- When idle, shows "No active jobs" with last completed job summary.

## Interaction Rules
- No scroll in any view; all lists are capped with "+N more".
- Stage actions disabled while the same stage job is running.
- Error states are inline and non-blocking.

## Responsive Behavior
- Desktop: 2-column layout (main + status rail).
- Tablet: status rail collapses into a horizontal footer strip.
- Mobile: stage tabs collapse to a selector; stage content becomes single column.

## Visual System (Tailwind + Radix)
- Tailwind theme tokens for colors, radii, spacing.
- Radix Tabs and Progress for accessibility and focus management.
- Consistent card heights to prevent layout shifts.

## Frontend Visual Testing (Playwright)
- Screenshot scenarios:
  - Empty state
  - Running job
  - Completed state
  - Error state
- Viewports:
  - Desktop, tablet, mobile
- Artifacts:
  - Saved screenshots per stage/state/viewport.
- Review loop:
  - Human-in-the-loop review of screenshots to confirm no-scroll layout and clarity.
