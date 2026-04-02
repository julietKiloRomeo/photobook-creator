# Step 6 - Chapters, Pages, and Export (Completed)

**Goal:** Let users assemble the book and preview/export it.

**Work:**
- Chapters/themes with ordering and page counts
- Staging area that can pull from multiple chapters
- Page layout with drag/drop photos and text elements
- Reuse photos across chapters and pages
- Text elements with basic styles (title, caption)
- Preview mode and export (photos + texts per page)

**Notes:**
- Store chapters/pages in SQLite tables already outlined in `SPECS.md`.
- Keep layouts as normalized units (0-1) to avoid hardcoding page sizes.
- Export format: JSON with chapter/page structure and resolved photo paths.

**Done When:**
- Users can create/reorder chapters and set page counts
- Users can place photos + text elements on pages
- Export file matches the page layout and references valid photos
