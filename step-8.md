# Step 8 - Framework UI + Flat Minimal Redesign

## Goal
Adopt a CSS framework and redesign the UI to be clean, flat, and guided (similar in clarity and simplicity to the provided references), while keeping users in control with gentle auto-advance.

## Framework Choice
- **Tailwind CSS** (utility-first, fast iteration, consistent spacing/typography).
- Use **Headless UI** (optional) for tabs/drawers if needed, but keep UI minimal.

## Design Principles (from references)
- Flat surfaces, minimal shadows, low contrast borders.
- Large whitespace, strong typographic hierarchy.
- One primary action per stage; remove redundant buttons.
- Clear status feedback instead of explanatory paragraphs.

## User-Story Alignment
1. **Intake & sources**: single dropzone supporting folders/photos/URLs.
2. **Non-destructive processing**: visible progress + resume, no extra clicks.
3. **Cross-source clustering**: clusters front and center with one action.
4. **Duplicate stacks**: guided best-shot selection, minimal controls.
5. **Staging area**: always accessible in Build.
6. **Book structure & pages**: clear chapter/page controls.
7. **Reuse & text**: simple add/drag affordances.
8. **Preview + export**: concise summary + export action.

## Implementation Plan

### 1) Add Tailwind
- Install Tailwind + PostCSS in `ui/`.
- Configure `tailwind.config.js` with a minimal palette inspired by the references.
- Replace custom CSS utilities gradually; keep only small app-specific styles.

### 2) Global Layout + Theme
- Header: project title + stage tabs + compact status pill (no tagline).
- App background: flat off-white with subtle panel borders.
- Typography: one strong display face + one clean sans for body.
- Spacing: consistent 4/8/12/16/24 rhythm.

### 3) Intake (single dropzone)
- Replace multi-button intake with one full-width dropzone.
- Show upload progress inline (thin progress bar + “Processing…”).
- Auto-advance to Clean when thumbnails exist.

### 4) Clean (best-shot focus)
- Large thumbnail grid; real thumbnails.
- Left: stack list with progress (e.g., “3/11 done”).
- Center: selected stack with real thumbnails and “Best” toggle on each image.
- Auto-run dedupe after thumbnails complete; no “Find duplicates” button.

### 5) Organize (clusters)
- Show clusters in a clean list; one CTA: “Create chapter from cluster”.
- Auto-advance to Build when at least one chapter exists.

### 6) Build (staging + canvas)
- Three-column layout: chapters/pages | canvas | staging palette.
- Staging palette searchable across themes; reuse allowed.
- Minimal controls; no heavy panels.

### 7) Export (flat summary)
- Flat panel summary + single export button.
- Provide simple preview list of chapters/pages.

### 8) Auto-advance + user control
- Auto-advance only when the system can conclude “done” for a stage.
- Animate transitions (fade/slide ~200ms).
- Show a small “Moved to Clean · Back” pill for 5 seconds.
- Stage tabs always allow manual navigation.

## Deliverables
- Tailwind integration in `ui/`.
- Updated `App.jsx` layout with minimal actions per stage.
- Clean, flat UI aligned with provided references.
- Stage transitions and auto-advance behavior.

## Done When
- Intake has only one visible action (dropzone) and auto-advances.
- Clean makes the “best shot” task obvious without extra buttons.
- Organize and Build follow the user stories with clear, minimal affordances.
- UI looks flat, simple, and consistent with reference screenshots.
