"""Auto-build: turn themes + stacks into a draft book.

For each theme, walks its assigned stacks (in stack creation order),
chunks them into pages of 4 slots, and fills each slot with the
stack's picked reference. If a stack has no pick yet but is a
single-photo stack, that lone photo is used. Pending multi-photo stacks
are skipped (the user hasn't decided yet).

This is mechanical, not "intelligent" — the family does the curating.
Auto-build's job is just to remove the chore of creating pages and
dragging the obvious choices in.
"""

from __future__ import annotations

import json

from shoebox.store import connection, dao

SLOTS_PER_PAGE = 4
DEFAULT_LAYOUT = "grid-2x2"

# Normalized positions for the 4 slots of a 2x2 grid.
_POSITIONS = [
    {"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5},
    {"x": 0.5, "y": 0.0, "w": 0.5, "h": 0.5},
    {"x": 0.0, "y": 0.5, "w": 0.5, "h": 0.5},
    {"x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5},
]


def auto_build(project_id: str) -> dict:
    """Build a fresh draft book for the project. Returns a small summary.

    Existing pages and items in the project's themes are cleared first
    so the rebuild is idempotent.
    """
    summary = {"themes": 0, "pages": 0, "items": 0}
    with connection() as conn:
        themes = dao.list_themes(conn, project_id)
        for theme in themes:
            # Clear existing pages for this theme (cascades to items).
            for existing_page in dao.list_pages(conn, theme["id"]):
                conn.execute("DELETE FROM pages WHERE id = ?", (existing_page["id"],))

            stack_ids = dao.list_stack_ids_for_theme(conn, theme["id"])
            picks: list[str] = []
            for sid in stack_ids:
                stack = dao.get_stack(conn, sid)
                if stack is None:
                    continue
                if stack["picked_reference_id"]:
                    picks.append(stack["picked_reference_id"])
                elif len(stack["reference_ids"]) == 1:
                    picks.append(stack["reference_ids"][0])
                # multi-photo pending stacks: user hasn't decided, skip.

            if not picks:
                continue
            summary["themes"] += 1

            for chunk_start in range(0, len(picks), SLOTS_PER_PAGE):
                chunk = picks[chunk_start : chunk_start + SLOTS_PER_PAGE]
                page = dao.create_page(conn, theme_id=theme["id"], layout_id=DEFAULT_LAYOUT)
                summary["pages"] += 1
                for slot, ref_id in enumerate(chunk):
                    dao.add_page_item(
                        conn,
                        page_id=page["id"],
                        kind="photo",
                        slot_index=slot,
                        reference_id=ref_id,
                        position_json=json.dumps(_POSITIONS[slot]),
                    )
                    summary["items"] += 1
    return summary
