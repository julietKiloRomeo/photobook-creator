from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from photobook.project_store import (
    assign_stack_theme,
    auto_build_book,
    chapter_exists,
    create_chapter,
    create_page_item,
    create_theme,
    ensure_schema,
    item_exists,
    list_chapters,
    list_page_items,
    list_pages,
    list_pages_with_items,
    list_references,
    list_stacks,
    list_themes,
    list_timeline_items,
    page_exists,
    pick_stack_reference,
    reference_exists,
    seed_demo_references_if_empty,
    reorder_chapters,
    sync_pages_for_chapter,
    theme_exists,
    update_chapter_name,
    update_page_item,
    update_theme,
    upsert_references,
)


DEFAULT_DB_PATH = ".photobook-temp/project.db"


class IntakeReferenceInput(BaseModel):
    source: str
    source_type: Literal["path", "uri"] = "path"
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntakeReferencesUpsertRequest(BaseModel):
    items: list[IntakeReferenceInput]


class ChapterCreateRequest(BaseModel):
    name: str
    page_count: int = 0


class ChapterUpdateRequest(BaseModel):
    name: str | None = None


class ChapterReorderRequest(BaseModel):
    chapter_ids: list[int]


class ChapterPagesRequest(BaseModel):
    page_count: int


class PageItemCreateRequest(BaseModel):
    item_type: Literal["photo", "text"]
    reference_id: int | None = None
    text: str | None = None
    x: float
    y: float
    w: float
    h: float
    z: int = 0


class PageItemUpdateRequest(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    z: int | None = None
    text: str | None = None
    reference_id: int | None = None


class ExportRequest(BaseModel):
    chapter_ids: list[int] | None = None


class DuelPickRequest(BaseModel):
    stack_id: str | None = None
    reference_id: int | None = None
    pick_id: str | int | None = None


class ThemeCreateRequest(BaseModel):
    title: str = "New theme"
    color: str | None = None


class ThemePatchRequest(BaseModel):
    title: str | None = None
    color: str | None = None
    stack_ids: list[str] | None = None


class ThemeAssignRequest(BaseModel):
    stack_id: str
    theme_id: int | None = None


def get_db_path() -> Path:
    return Path(os.getenv("PHOTOBOOK_DB_PATH", DEFAULT_DB_PATH))


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def create_app() -> FastAPI:
    app = FastAPI(title="Photo Book Creator API")

    frontend_dir = _root_dir() / "frontend"
    if frontend_dir.exists():
        app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

    def _ensure() -> Path:
        db_path = get_db_path()
        ensure_schema(db_path)
        if os.getenv("PHOTOBOOK_DB_PATH") is None:
            seed_demo_references_if_empty(db_path, _root_dir())
        return db_path

    @app.get("/")
    def ui_shell() -> FileResponse:
        html_path = _root_dir() / "darkroom_v2.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="darkroom_v2.html not found")
        return FileResponse(html_path)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        db_path = _ensure()
        return {
            "status": "ok",
            "db_path": str(db_path),
        }

    @app.get("/api/intake/references")
    def get_references() -> JSONResponse:
        db_path = _ensure()
        return JSONResponse({"items": list_references(db_path)})

    @app.post("/api/intake/references")
    def post_references(payload: IntakeReferencesUpsertRequest) -> JSONResponse:
        if not payload.items:
            return JSONResponse({"items": []})

        db_path = _ensure()
        items = upsert_references(db_path, [item.model_dump() for item in payload.items])
        return JSONResponse({"items": items})

    @app.get("/api/stacks")
    def get_stacks() -> JSONResponse:
        db_path = _ensure()
        return JSONResponse({"items": list_stacks(db_path)})

    @app.post("/api/duel/pick")
    def post_duel_pick(payload: DuelPickRequest) -> JSONResponse:
        db_path = _ensure()
        stack_id = payload.stack_id
        reference_id = payload.reference_id

        if reference_id is None and payload.pick_id is not None:
            if isinstance(payload.pick_id, int):
                reference_id = payload.pick_id
            elif isinstance(payload.pick_id, str):
                digits = "".join(ch for ch in payload.pick_id if ch.isdigit())
                if digits:
                    reference_id = int(digits)

        if stack_id is None or reference_id is None:
            return JSONResponse({"status": "ignored", "reason": "missing_stack_or_reference"})

        if not reference_exists(db_path, reference_id):
            return JSONResponse({"status": "ignored", "reason": "reference_not_found"})

        stacks = list_stacks(db_path)
        stack = next((item for item in stacks if item["id"] == stack_id), None)
        if stack is None:
            return JSONResponse({"status": "ignored", "reason": "stack_not_found"})
        if reference_id not in stack["photo_ids"]:
            return JSONResponse({"status": "ignored", "reason": "reference_not_in_stack"})

        pick_stack_reference(db_path, stack_id, reference_id)
        updated = next((item for item in list_stacks(db_path) if item["id"] == stack_id), None)
        return JSONResponse({"item": updated or {"id": stack_id}})

    @app.get("/api/themes")
    def get_themes() -> JSONResponse:
        db_path = _ensure()
        return JSONResponse({"items": list_themes(db_path)})

    @app.post("/api/themes")
    def post_theme(payload: ThemeCreateRequest) -> JSONResponse:
        db_path = _ensure()
        created = create_theme(db_path, payload.title, payload.color)
        return JSONResponse(created, status_code=201)

    @app.patch("/api/themes/{theme_id}")
    def patch_theme(theme_id: int, payload: ThemePatchRequest) -> JSONResponse:
        db_path = _ensure()
        if not theme_exists(db_path, theme_id):
            raise HTTPException(status_code=404, detail="Theme not found")

        updated = update_theme(db_path, theme_id, payload.model_dump(exclude_unset=True))
        return JSONResponse(updated)

    @app.post("/api/themes/assign")
    def post_theme_assignment(payload: ThemeAssignRequest) -> JSONResponse:
        db_path = _ensure()
        if payload.theme_id is not None and not theme_exists(db_path, payload.theme_id):
            raise HTTPException(status_code=404, detail="Theme not found")

        assign_stack_theme(db_path, payload.stack_id, payload.theme_id)
        return JSONResponse({"status": "ok"})

    @app.get("/api/timeline")
    def get_timeline() -> JSONResponse:
        db_path = _ensure()
        return JSONResponse({"items": list_timeline_items(db_path)})

    @app.get("/api/chapters")
    def get_chapters() -> JSONResponse:
        db_path = _ensure()
        return JSONResponse({"items": list_chapters(db_path)})

    @app.post("/api/chapters")
    def post_chapter(payload: ChapterCreateRequest) -> JSONResponse:
        db_path = _ensure()
        chapter_id = create_chapter(db_path, payload.name, page_count=payload.page_count)
        chapters = list_chapters(db_path)
        created = next((item for item in chapters if item["id"] == chapter_id), None)
        return JSONResponse(created or {"id": chapter_id}, status_code=201)

    @app.patch("/api/chapters/{chapter_id}")
    def patch_chapter(chapter_id: int, payload: ChapterUpdateRequest) -> JSONResponse:
        db_path = _ensure()
        if not chapter_exists(db_path, chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")

        update_chapter_name(db_path, chapter_id, payload.name)
        chapters = list_chapters(db_path)
        updated = next((item for item in chapters if item["id"] == chapter_id), None)
        return JSONResponse(updated or {"id": chapter_id})

    @app.post("/api/chapters/reorder")
    def post_reorder(payload: ChapterReorderRequest) -> JSONResponse:
        db_path = _ensure()
        reorder_chapters(db_path, payload.chapter_ids)
        return JSONResponse({"status": "ok"})

    @app.get("/api/chapters/{chapter_id}/pages")
    def get_pages(chapter_id: int) -> JSONResponse:
        db_path = _ensure()
        if not chapter_exists(db_path, chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        return JSONResponse({"items": list_pages(db_path, chapter_id)})

    @app.post("/api/chapters/{chapter_id}/pages")
    def post_pages(chapter_id: int, payload: ChapterPagesRequest) -> JSONResponse:
        db_path = _ensure()
        if not chapter_exists(db_path, chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        sync_pages_for_chapter(db_path, chapter_id, payload.page_count)
        return JSONResponse({"items": list_pages(db_path, chapter_id)})

    @app.get("/api/pages/{page_id}/items")
    def get_page_items(page_id: int) -> JSONResponse:
        db_path = _ensure()
        if not page_exists(db_path, page_id):
            raise HTTPException(status_code=404, detail="Page not found")
        return JSONResponse({"items": list_page_items(db_path, page_id)})

    @app.post("/api/pages/{page_id}/items")
    def post_page_item(page_id: int, payload: PageItemCreateRequest) -> JSONResponse:
        db_path = _ensure()
        if not page_exists(db_path, page_id):
            raise HTTPException(status_code=404, detail="Page not found")

        if payload.item_type == "photo" and payload.reference_id is None:
            raise HTTPException(status_code=400, detail="Photo items require reference_id")
        if payload.item_type == "text" and not (payload.text or "").strip():
            raise HTTPException(status_code=400, detail="Text items require text")
        if payload.reference_id is not None and not reference_exists(db_path, payload.reference_id):
            raise HTTPException(status_code=400, detail="Reference not found")

        item_id = create_page_item(db_path, page_id, payload.model_dump())
        items = list_page_items(db_path, page_id)
        created = next((item for item in items if item["id"] == item_id), None)
        return JSONResponse(created or {"id": item_id}, status_code=201)

    @app.patch("/api/pages/items/{item_id}")
    def patch_page_item(item_id: int, payload: PageItemUpdateRequest) -> JSONResponse:
        db_path = _ensure()
        if not item_exists(db_path, item_id):
            raise HTTPException(status_code=404, detail="Page item not found")

        updates = payload.model_dump(exclude_unset=True)
        if "reference_id" in updates and updates["reference_id"] is not None:
            if not reference_exists(db_path, int(updates["reference_id"])):
                raise HTTPException(status_code=400, detail="Reference not found")

        update_page_item(db_path, item_id, updates)
        return JSONResponse({"status": "ok"})

    @app.post("/api/book/auto-build")
    def post_auto_build() -> JSONResponse:
        db_path = _ensure()
        chapters = auto_build_book(db_path)
        return JSONResponse({"chapters": chapters})

    @app.post("/api/export")
    def export(payload: ExportRequest) -> JSONResponse:
        db_path = _ensure()
        chapters = list_pages_with_items(db_path, payload.chapter_ids)
        references = list_references(db_path)
        if payload.chapter_ids is None and not chapters and references:
            chapters = auto_build_book(db_path)
        return JSONResponse(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapters": chapters,
                "references": references,
            }
        )

    return app
