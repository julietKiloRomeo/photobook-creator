"""JSON export.

Produces a single self-contained ZIP that the owner can carry to any
print vendor (Pixum, Mixbook, …). The ZIP layout:

    book.json
    assets/<file_hash>.<ext>          (full resolution originals)

``book.json`` is versioned and stable: schema_version=1.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from shoebox import __version__
from shoebox.store import connection, dao

SCHEMA_VERSION = 1


def build_export_bundle(project_id: str) -> tuple[bytes, str]:
    """Build the export ZIP for a project.

    Returns ``(bytes, filename_suggestion)``.
    """
    with connection() as conn:
        project = dao.get_project(conn, project_id)
        if project is None:
            raise ValueError(f"Unknown project: {project_id!r}")
        references = dao.list_references(conn, project_id)
        themes = dao.list_themes(conn, project_id)

        # Build the structure first; collect asset paths as we go.
        ref_by_id: dict[str, dict] = {r["id"]: r for r in references}
        used_ref_ids: set[str] = set()
        themes_json: list[dict[str, Any]] = []

        for theme in themes:
            pages = dao.list_pages(conn, theme["id"])
            pages_json: list[dict[str, Any]] = []
            for page in pages:
                items = dao.list_page_items(conn, page["id"])
                items_json: list[dict[str, Any]] = []
                for item in items:
                    if item["kind"] == "photo":
                        ref = ref_by_id.get(item["reference_id"]) if item["reference_id"] else None
                        if ref is None:
                            continue
                        used_ref_ids.add(ref["id"])
                        items_json.append(
                            {
                                "kind": "photo",
                                "slot": item["slot_index"],
                                "asset": f"assets/{_asset_filename(ref)}",
                                "position": json.loads(item["position_json"] or "{}"),
                            }
                        )
                    elif item["kind"] == "text":
                        items_json.append(
                            {
                                "kind": "text",
                                "slot": item["slot_index"],
                                "content": item["text_content"] or "",
                                "position": json.loads(item["position_json"] or "{}"),
                            }
                        )
                pages_json.append(
                    {
                        "id": page["id"],
                        "order": page["order_index"],
                        "layout_id": page["layout_id"],
                        "items": items_json,
                    }
                )

            themes_json.append(
                {
                    "id": theme["id"],
                    "name": theme["name"],
                    "color": theme["color"],
                    "order": theme["order_index"],
                    "pages": pages_json,
                }
            )

        assets_json = []
        for ref_id in sorted(used_ref_ids):
            ref = ref_by_id[ref_id]
            assets_json.append(
                {
                    "path": f"assets/{_asset_filename(ref)}",
                    "sha256": ref["file_hash"],
                    "captured_at": ref.get("captured_at"),
                    "width": ref.get("width"),
                    "height": ref.get("height"),
                }
            )

    book = {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": "shoebox", "version": __version__},
        "project": {
            "id": project["id"],
            "name": project["name"],
            "created_at": project["created_at"],
        },
        "themes": themes_json,
        "assets": assets_json,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("book.json", json.dumps(book, indent=2))
        for ref_id in used_ref_ids:
            ref = ref_by_id[ref_id]
            source = Path(ref["original_path"])
            if source.exists():
                zf.write(source, arcname=f"assets/{_asset_filename(ref)}")

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project["name"]).strip("_")
    filename = f"shoebox-{safe_name or 'project'}.zip"
    return buffer.getvalue(), filename


def _asset_filename(reference: dict) -> str:
    suffix = Path(reference["original_path"]).suffix.lower() or ".jpg"
    return f"{reference['file_hash']}{suffix}"
