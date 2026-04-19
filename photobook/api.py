from __future__ import annotations

from datetime import datetime, timezone
import mimetypes
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from photobook.clustering import run_clustering_pipeline
from photobook.project_store import (
    assign_stack_theme,
    auto_build_book,
    chapter_exists,
    create_chapter,
    create_page_item,
    create_theme,
    delete_theme,
    ensure_schema,
    get_reference,
    item_exists,
    list_chapters,
    list_duplicate_groups,
    list_page_items,
    list_pages,
    list_pages_with_items,
    list_references,
    list_stacks,
    list_themes,
    list_timeline_items,
    list_uploads,
    page_exists,
    pick_stack_reference,
    reference_exists,
    reorder_chapters,
    sync_pages_for_chapter,
    theme_exists,
    update_chapter_name,
    update_page_item,
    update_theme,
    upsert_references,
)
from photobook.projects_index import (
    create_project,
    ensure_default_project,
    get_project,
    get_project_db_path,
    get_project_derived_dir,
    get_project_originals_dir,
    list_projects,
    reset_project_storage,
)
from photobook.uploads import process_uploads


DEFAULT_DB_PATH = ".photobook-temp/project.db"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


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


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _external_db_path() -> Path | None:
    raw = os.getenv("PHOTOBOOK_DB_PATH")
    if raw:
        return Path(raw)
    return None


def _ctx(project_id: str | None) -> dict[str, Any]:
    external_db = _external_db_path()
    if project_id == "external" and external_db is not None:
        db_path = external_db
        ensure_schema(db_path)
        return {
            "project": None,
            "project_id": "external",
            "db_path": db_path,
            "originals_dir": db_path.parent / "originals",
            "derived_dir": db_path.parent / "derived",
        }
    if project_id is None and external_db is not None:
        db_path = external_db
        ensure_schema(db_path)
        return {
            "project": None,
            "project_id": None,
            "db_path": db_path,
            "originals_dir": db_path.parent / "originals",
            "derived_dir": db_path.parent / "derived",
        }

    if project_id is None:
        project = ensure_default_project()
    else:
        project = get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    pid = str(project["id"])
    db_path = get_project_db_path(pid)
    originals_dir = get_project_originals_dir(pid)
    derived_dir = get_project_derived_dir(pid)
    originals_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)
    ensure_schema(db_path)
    return {
        "project": project,
        "project_id": pid,
        "db_path": db_path,
        "originals_dir": originals_dir,
        "derived_dir": derived_dir,
    }


def _parse_duel_reference(payload: DuelPickRequest) -> tuple[str | None, int | None]:
    stack_id = payload.stack_id
    reference_id = payload.reference_id
    if reference_id is None and payload.pick_id is not None:
        if isinstance(payload.pick_id, int):
            reference_id = payload.pick_id
        elif isinstance(payload.pick_id, str):
            digits = "".join(ch for ch in payload.pick_id if ch.isdigit())
            if digits:
                reference_id = int(digits)
    return stack_id, reference_id


def _post_duel_pick(db_path: Path, payload: DuelPickRequest) -> JSONResponse:
    stack_id, reference_id = _parse_duel_reference(payload)
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


def _reference_image_response(db_path: Path, reference_id: int) -> FileResponse:
    reference = get_reference(db_path, reference_id)
    if reference is None:
        raise HTTPException(status_code=404, detail="Reference not found")

    source = str(reference.get("source") or "").strip()
    if not source:
        raise HTTPException(status_code=404, detail="Reference source missing")

    path = Path(source)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Reference file not found")

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


def create_app() -> FastAPI:
    app = FastAPI(title="Photo Book Creator API")

    frontend_dir = _root_dir() / "frontend"
    if frontend_dir.exists():
        app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

    @app.get("/")
    def projects_shell() -> FileResponse:
        html_path = _root_dir() / "index.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(html_path)

    @app.get("/darkroom")
    def darkroom_default() -> RedirectResponse:
        if _external_db_path() is not None:
            # External DB compatibility mode keeps old single-project behavior.
            return RedirectResponse(url="/darkroom/external")
        project = ensure_default_project()
        return RedirectResponse(url=f"/darkroom/{project['id']}")

    @app.get("/darkroom/{project_id}")
    def darkroom_shell(project_id: str) -> FileResponse:
        if project_id != "external":
            _ctx(project_id)
        html_path = _root_dir() / "darkroom_v2.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="darkroom_v2.html not found")
        return FileResponse(html_path)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        ctx = _ctx(None)
        return {
            "status": "ok",
            "db_path": str(ctx["db_path"]),
            "project_id": ctx["project_id"] or "external",
        }

    @app.get("/api/projects")
    def get_projects() -> JSONResponse:
        return JSONResponse({"items": list_projects()})

    @app.post("/api/projects")
    def post_project(payload: ProjectCreateRequest) -> JSONResponse:
        project = create_project(payload.name.strip())
        return JSONResponse(project, status_code=201)

    @app.get("/api/projects/{project_id}")
    def get_project_details(project_id: str) -> JSONResponse:
        project = get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return JSONResponse(project)

    @app.get("/api/projects/{project_id}/uploads")
    def get_project_uploads(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_uploads(ctx["db_path"])})

    @app.post("/api/projects/{project_id}/uploads")
    async def post_project_uploads(
        project_id: str,
        files: list[UploadFile] = File(...),
        relative_paths: list[str] = Form(default=[]),
    ) -> JSONResponse:
        if not files:
            return JSONResponse({"upload": {"stored": 0, "supported_images": 0, "ignored": 0, "created_references": 0}})

        ctx = _ctx(project_id)
        result = process_uploads(
            ctx["db_path"],
            originals_dir=ctx["originals_dir"],
            derived_dir=ctx["derived_dir"],
            files=files,
            relative_paths=relative_paths,
        )
        processing = run_clustering_pipeline(ctx["db_path"])
        return JSONResponse(
            {
                "upload": {
                    "stored": result.stored,
                    "supported_images": result.supported_images,
                    "ignored": result.ignored,
                    "created_references": result.created_references,
                },
                "processing": processing,
            }
        )

    @app.get("/api/projects/{project_id}/references/{reference_id}/image")
    def get_project_reference_image(project_id: str, reference_id: int) -> FileResponse:
        ctx = _ctx(project_id)
        return _reference_image_response(ctx["db_path"], reference_id)

    @app.post("/api/projects/{project_id}/process")
    def post_project_process(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        summary = run_clustering_pipeline(ctx["db_path"])
        return JSONResponse({"summary": summary})

    @app.get("/api/projects/{project_id}/duplicates")
    def get_project_duplicates(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_duplicate_groups(ctx["db_path"])})

    @app.post("/api/projects/{project_id}/reset")
    def post_project_reset(project_id: str) -> JSONResponse:
        project = get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        reset_project_storage(project_id)
        ctx = _ctx(project_id)
        return JSONResponse({"status": "ok", "project_id": project_id, "db_path": str(ctx["db_path"])})

    # Project-scoped API surface.
    @app.get("/api/projects/{project_id}/intake/references")
    def get_project_references(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_references(ctx["db_path"])})

    @app.post("/api/projects/{project_id}/intake/references")
    def post_project_references(project_id: str, payload: IntakeReferencesUpsertRequest) -> JSONResponse:
        if not payload.items:
            return JSONResponse({"items": []})
        ctx = _ctx(project_id)
        items = upsert_references(ctx["db_path"], [item.model_dump() for item in payload.items])
        return JSONResponse({"items": items})

    @app.get("/api/projects/{project_id}/stacks")
    def get_project_stacks(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_stacks(ctx["db_path"])})

    @app.post("/api/projects/{project_id}/duel/pick")
    def post_project_duel_pick(project_id: str, payload: DuelPickRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        return _post_duel_pick(ctx["db_path"], payload)

    @app.get("/api/projects/{project_id}/themes")
    def get_project_themes(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_themes(ctx["db_path"])})

    @app.post("/api/projects/{project_id}/themes")
    def post_project_theme(project_id: str, payload: ThemeCreateRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        created = create_theme(ctx["db_path"], payload.title, payload.color)
        return JSONResponse(created, status_code=201)

    @app.patch("/api/projects/{project_id}/themes/{theme_id}")
    def patch_project_theme(project_id: str, theme_id: int, payload: ThemePatchRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        if not theme_exists(ctx["db_path"], theme_id):
            raise HTTPException(status_code=404, detail="Theme not found")
        updated = update_theme(ctx["db_path"], theme_id, payload.model_dump(exclude_unset=True))
        return JSONResponse(updated)

    @app.delete("/api/projects/{project_id}/themes/{theme_id}")
    def delete_project_theme(project_id: str, theme_id: int) -> JSONResponse:
        ctx = _ctx(project_id)
        delete_theme(ctx["db_path"], theme_id)
        return JSONResponse({"status": "ok"})

    @app.post("/api/projects/{project_id}/themes/assign")
    def assign_project_theme(project_id: str, payload: ThemeAssignRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        if payload.theme_id is not None and not theme_exists(ctx["db_path"], payload.theme_id):
            raise HTTPException(status_code=404, detail="Theme not found")
        assign_stack_theme(ctx["db_path"], payload.stack_id, payload.theme_id)
        return JSONResponse({"status": "ok"})

    @app.get("/api/projects/{project_id}/timeline")
    def get_project_timeline(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_timeline_items(ctx["db_path"])})

    @app.get("/api/projects/{project_id}/chapters")
    def get_project_chapters(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        return JSONResponse({"items": list_chapters(ctx["db_path"])})

    @app.post("/api/projects/{project_id}/chapters")
    def post_project_chapter(project_id: str, payload: ChapterCreateRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        chapter_id = create_chapter(ctx["db_path"], payload.name, page_count=payload.page_count)
        chapters = list_chapters(ctx["db_path"])
        created = next((item for item in chapters if item["id"] == chapter_id), None)
        return JSONResponse(created or {"id": chapter_id}, status_code=201)

    @app.patch("/api/projects/{project_id}/chapters/{chapter_id}")
    def patch_project_chapter(project_id: str, chapter_id: int, payload: ChapterUpdateRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        if not chapter_exists(ctx["db_path"], chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        update_chapter_name(ctx["db_path"], chapter_id, payload.name)
        chapters = list_chapters(ctx["db_path"])
        updated = next((item for item in chapters if item["id"] == chapter_id), None)
        return JSONResponse(updated or {"id": chapter_id})

    @app.post("/api/projects/{project_id}/chapters/reorder")
    def reorder_project_chapters(project_id: str, payload: ChapterReorderRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        reorder_chapters(ctx["db_path"], payload.chapter_ids)
        return JSONResponse({"status": "ok"})

    @app.get("/api/projects/{project_id}/chapters/{chapter_id}/pages")
    def get_project_pages(project_id: str, chapter_id: int) -> JSONResponse:
        ctx = _ctx(project_id)
        if not chapter_exists(ctx["db_path"], chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        return JSONResponse({"items": list_pages(ctx["db_path"], chapter_id)})

    @app.post("/api/projects/{project_id}/chapters/{chapter_id}/pages")
    def post_project_pages(project_id: str, chapter_id: int, payload: ChapterPagesRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        if not chapter_exists(ctx["db_path"], chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        sync_pages_for_chapter(ctx["db_path"], chapter_id, payload.page_count)
        return JSONResponse({"items": list_pages(ctx["db_path"], chapter_id)})

    @app.get("/api/projects/{project_id}/pages/{page_id}/items")
    def get_project_page_items(project_id: str, page_id: int) -> JSONResponse:
        ctx = _ctx(project_id)
        if not page_exists(ctx["db_path"], page_id):
            raise HTTPException(status_code=404, detail="Page not found")
        return JSONResponse({"items": list_page_items(ctx["db_path"], page_id)})

    @app.post("/api/projects/{project_id}/pages/{page_id}/items")
    def post_project_page_item(project_id: str, page_id: int, payload: PageItemCreateRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        if not page_exists(ctx["db_path"], page_id):
            raise HTTPException(status_code=404, detail="Page not found")

        if payload.item_type == "photo" and payload.reference_id is None:
            raise HTTPException(status_code=400, detail="Photo items require reference_id")
        if payload.item_type == "text" and not (payload.text or "").strip():
            raise HTTPException(status_code=400, detail="Text items require text")
        if payload.reference_id is not None and not reference_exists(ctx["db_path"], payload.reference_id):
            raise HTTPException(status_code=400, detail="Reference not found")

        item_id = create_page_item(ctx["db_path"], page_id, payload.model_dump())
        items = list_page_items(ctx["db_path"], page_id)
        created = next((item for item in items if item["id"] == item_id), None)
        return JSONResponse(created or {"id": item_id}, status_code=201)

    @app.patch("/api/projects/{project_id}/pages/items/{item_id}")
    def patch_project_page_item(project_id: str, item_id: int, payload: PageItemUpdateRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        if not item_exists(ctx["db_path"], item_id):
            raise HTTPException(status_code=404, detail="Page item not found")

        updates = payload.model_dump(exclude_unset=True)
        if "reference_id" in updates and updates["reference_id"] is not None:
            if not reference_exists(ctx["db_path"], int(updates["reference_id"])):
                raise HTTPException(status_code=400, detail="Reference not found")

        update_page_item(ctx["db_path"], item_id, updates)
        return JSONResponse({"status": "ok"})

    @app.post("/api/projects/{project_id}/book/auto-build")
    def post_project_auto_build(project_id: str) -> JSONResponse:
        ctx = _ctx(project_id)
        chapters = auto_build_book(ctx["db_path"])
        return JSONResponse({"chapters": chapters})

    @app.post("/api/projects/{project_id}/export")
    def post_project_export(project_id: str, payload: ExportRequest) -> JSONResponse:
        ctx = _ctx(project_id)
        chapters = list_pages_with_items(ctx["db_path"], payload.chapter_ids)
        references = list_references(ctx["db_path"])
        if payload.chapter_ids is None and not chapters and references:
            chapters = auto_build_book(ctx["db_path"])
        return JSONResponse(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapters": chapters,
                "references": references,
            }
        )

    # Compatibility aliases against the default project/external DB.
    @app.get("/api/intake/references")
    def get_references() -> JSONResponse:
        ctx = _ctx(None)
        return JSONResponse({"items": list_references(ctx["db_path"])})

    @app.post("/api/intake/references")
    def post_references(payload: IntakeReferencesUpsertRequest) -> JSONResponse:
        if not payload.items:
            return JSONResponse({"items": []})
        ctx = _ctx(None)
        items = upsert_references(ctx["db_path"], [item.model_dump() for item in payload.items])
        return JSONResponse({"items": items})

    @app.get("/api/references/{reference_id}/image")
    def get_reference_image(reference_id: int) -> FileResponse:
        ctx = _ctx(None)
        return _reference_image_response(ctx["db_path"], reference_id)

    @app.get("/api/stacks")
    def get_stacks() -> JSONResponse:
        ctx = _ctx(None)
        return JSONResponse({"items": list_stacks(ctx["db_path"])})

    @app.post("/api/duel/pick")
    def post_duel_pick(payload: DuelPickRequest) -> JSONResponse:
        ctx = _ctx(None)
        return _post_duel_pick(ctx["db_path"], payload)

    @app.get("/api/themes")
    def get_themes() -> JSONResponse:
        ctx = _ctx(None)
        return JSONResponse({"items": list_themes(ctx["db_path"])})

    @app.post("/api/themes")
    def post_theme(payload: ThemeCreateRequest) -> JSONResponse:
        ctx = _ctx(None)
        created = create_theme(ctx["db_path"], payload.title, payload.color)
        return JSONResponse(created, status_code=201)

    @app.patch("/api/themes/{theme_id}")
    def patch_theme(theme_id: int, payload: ThemePatchRequest) -> JSONResponse:
        ctx = _ctx(None)
        if not theme_exists(ctx["db_path"], theme_id):
            raise HTTPException(status_code=404, detail="Theme not found")
        updated = update_theme(ctx["db_path"], theme_id, payload.model_dump(exclude_unset=True))
        return JSONResponse(updated)

    @app.delete("/api/themes/{theme_id}")
    def remove_theme(theme_id: int) -> JSONResponse:
        ctx = _ctx(None)
        delete_theme(ctx["db_path"], theme_id)
        return JSONResponse({"status": "ok"})

    @app.post("/api/themes/assign")
    def post_theme_assignment(payload: ThemeAssignRequest) -> JSONResponse:
        ctx = _ctx(None)
        if payload.theme_id is not None and not theme_exists(ctx["db_path"], payload.theme_id):
            raise HTTPException(status_code=404, detail="Theme not found")
        assign_stack_theme(ctx["db_path"], payload.stack_id, payload.theme_id)
        return JSONResponse({"status": "ok"})

    @app.get("/api/timeline")
    def get_timeline() -> JSONResponse:
        ctx = _ctx(None)
        return JSONResponse({"items": list_timeline_items(ctx["db_path"])})

    @app.get("/api/chapters")
    def get_chapters() -> JSONResponse:
        ctx = _ctx(None)
        return JSONResponse({"items": list_chapters(ctx["db_path"])})

    @app.post("/api/chapters")
    def post_chapter(payload: ChapterCreateRequest) -> JSONResponse:
        ctx = _ctx(None)
        chapter_id = create_chapter(ctx["db_path"], payload.name, page_count=payload.page_count)
        chapters = list_chapters(ctx["db_path"])
        created = next((item for item in chapters if item["id"] == chapter_id), None)
        return JSONResponse(created or {"id": chapter_id}, status_code=201)

    @app.patch("/api/chapters/{chapter_id}")
    def patch_chapter(chapter_id: int, payload: ChapterUpdateRequest) -> JSONResponse:
        ctx = _ctx(None)
        if not chapter_exists(ctx["db_path"], chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        update_chapter_name(ctx["db_path"], chapter_id, payload.name)
        chapters = list_chapters(ctx["db_path"])
        updated = next((item for item in chapters if item["id"] == chapter_id), None)
        return JSONResponse(updated or {"id": chapter_id})

    @app.post("/api/chapters/reorder")
    def post_reorder(payload: ChapterReorderRequest) -> JSONResponse:
        ctx = _ctx(None)
        reorder_chapters(ctx["db_path"], payload.chapter_ids)
        return JSONResponse({"status": "ok"})

    @app.get("/api/chapters/{chapter_id}/pages")
    def get_pages(chapter_id: int) -> JSONResponse:
        ctx = _ctx(None)
        if not chapter_exists(ctx["db_path"], chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        return JSONResponse({"items": list_pages(ctx["db_path"], chapter_id)})

    @app.post("/api/chapters/{chapter_id}/pages")
    def post_pages(chapter_id: int, payload: ChapterPagesRequest) -> JSONResponse:
        ctx = _ctx(None)
        if not chapter_exists(ctx["db_path"], chapter_id):
            raise HTTPException(status_code=404, detail="Chapter not found")
        sync_pages_for_chapter(ctx["db_path"], chapter_id, payload.page_count)
        return JSONResponse({"items": list_pages(ctx["db_path"], chapter_id)})

    @app.get("/api/pages/{page_id}/items")
    def get_page_items(page_id: int) -> JSONResponse:
        ctx = _ctx(None)
        if not page_exists(ctx["db_path"], page_id):
            raise HTTPException(status_code=404, detail="Page not found")
        return JSONResponse({"items": list_page_items(ctx["db_path"], page_id)})

    @app.post("/api/pages/{page_id}/items")
    def post_page_item(page_id: int, payload: PageItemCreateRequest) -> JSONResponse:
        ctx = _ctx(None)
        if not page_exists(ctx["db_path"], page_id):
            raise HTTPException(status_code=404, detail="Page not found")

        if payload.item_type == "photo" and payload.reference_id is None:
            raise HTTPException(status_code=400, detail="Photo items require reference_id")
        if payload.item_type == "text" and not (payload.text or "").strip():
            raise HTTPException(status_code=400, detail="Text items require text")
        if payload.reference_id is not None and not reference_exists(ctx["db_path"], payload.reference_id):
            raise HTTPException(status_code=400, detail="Reference not found")

        item_id = create_page_item(ctx["db_path"], page_id, payload.model_dump())
        items = list_page_items(ctx["db_path"], page_id)
        created = next((item for item in items if item["id"] == item_id), None)
        return JSONResponse(created or {"id": item_id}, status_code=201)

    @app.patch("/api/pages/items/{item_id}")
    def patch_page_item(item_id: int, payload: PageItemUpdateRequest) -> JSONResponse:
        ctx = _ctx(None)
        if not item_exists(ctx["db_path"], item_id):
            raise HTTPException(status_code=404, detail="Page item not found")
        updates = payload.model_dump(exclude_unset=True)
        if "reference_id" in updates and updates["reference_id"] is not None:
            if not reference_exists(ctx["db_path"], int(updates["reference_id"])):
                raise HTTPException(status_code=400, detail="Reference not found")
        update_page_item(ctx["db_path"], item_id, updates)
        return JSONResponse({"status": "ok"})

    @app.post("/api/book/auto-build")
    def post_auto_build() -> JSONResponse:
        ctx = _ctx(None)
        chapters = auto_build_book(ctx["db_path"])
        return JSONResponse({"chapters": chapters})

    @app.post("/api/export")
    def export(payload: ExportRequest) -> JSONResponse:
        ctx = _ctx(None)
        chapters = list_pages_with_items(ctx["db_path"], payload.chapter_ids)
        references = list_references(ctx["db_path"])
        if payload.chapter_ids is None and not chapters and references:
            chapters = auto_build_book(ctx["db_path"])
        return JSONResponse(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapters": chapters,
                "references": references,
            }
        )

    return app
