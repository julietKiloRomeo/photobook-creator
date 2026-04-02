from __future__ import annotations

import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from photobook.project_store import (
    create_job,
    create_chapter,
    create_page_item,
    ensure_schema,
    get_job,
    list_clusters,
    list_chapters,
    list_duplicate_groups,
    list_page_items,
    list_pages,
    list_pages_with_items,
    list_photo_paths,
    list_photo_scores,
    list_thumbnail_paths,
    list_thumbnails,
    reorder_chapters,
    sync_pages_for_chapter,
    update_page_item,
    update_chapter,
    update_job_progress,
    update_job_status,
    upsert_thumbnail_records,
    ignore_duplicate_group,
    ignore_photo,
    list_duplicate_photo_paths,
    delete_photo_assets,
    set_duplicate_group_resolved,
)
from photobook.aesthetic_score import score_thumbnails
from photobook.clustering import cluster_photos_by_time
from photobook.dedupe import find_duplicate_groups
from photobook.thumbnails import (
    build_thumbnail_path,
    generate_thumbnail,
    to_thumbnail_record,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Photo Book Creator")
    executor = ThreadPoolExecutor(max_workers=2)

    class ChapterCreate(BaseModel):
        name: str
        page_count: int = 0

    class ChapterUpdate(BaseModel):
        name: str | None = None

    class ChapterReorder(BaseModel):
        chapter_ids: list[int]

    class ChapterPagesUpdate(BaseModel):
        page_count: int

    class PageItemCreate(BaseModel):
        item_type: str
        photo_path: str | None = None
        text: str | None = None
        x: float
        y: float
        w: float
        h: float
        z: int = 0

    class PageItemUpdate(BaseModel):
        x: float | None = None
        y: float | None = None
        w: float | None = None
        h: float | None = None
        z: int | None = None
        text: str | None = None
        photo_path: str | None = None

    class ExportRequest(BaseModel):
        chapter_ids: list[int] | None = None

    class IgnoreGroupRequest(BaseModel):
        group_id: int

    class IgnorePhotoRequest(BaseModel):
        photo_path: str

    class DeleteGroupRequest(BaseModel):
        group_id: int

    class DeletePhotoRequest(BaseModel):
        photo_path: str

    class ResolveGroupRequest(BaseModel):
        group_id: int
        resolved: bool = True

    def process_thumbnails(
        job_id: str,
        sources: list[Path],
        cluster_job_id: str | None = None,
    ) -> None:
        project_root = Path(".photobook-temp")
        cache_dir = project_root / "cache" / "thumbnails"
        db_path = project_root / "project.db"
        sizes = [256, 1024]

        update_job_status(db_path, job_id, "running")
        completed = 0
        try:
            for source in sources:
                for size in sizes:
                    output_path = build_thumbnail_path(cache_dir, source, size)
                    result = generate_thumbnail(source, output_path, size)
                    record = to_thumbnail_record(result)
                    upsert_thumbnail_records(db_path, [record])
                    completed += 1
                    update_job_progress(db_path, job_id, completed)
            update_job_status(db_path, job_id, "completed")
            if cluster_job_id:
                process_clusters(cluster_job_id)
        except Exception:
            update_job_status(db_path, job_id, "failed")
            if cluster_job_id:
                update_job_status(db_path, cluster_job_id, "failed")

    def process_clusters(job_id: str) -> None:
        db_path = Path(".photobook-temp") / "project.db"
        update_job_status(db_path, job_id, "running")
        try:
            total = len(list_photo_paths(db_path))
            cluster_photos_by_time(db_path)
            update_job_progress(db_path, job_id, total)
            update_job_status(db_path, job_id, "completed")
        except Exception:
            update_job_status(db_path, job_id, "failed")

    def process_dedupe(job_id: str) -> None:
        db_path = Path(".photobook-temp") / "project.db"
        update_job_status(db_path, job_id, "running")
        try:
            total = len(list_thumbnail_paths(db_path, 256))
            find_duplicate_groups(db_path)
            update_job_progress(db_path, job_id, total)
            update_job_status(db_path, job_id, "completed")
        except Exception:
            update_job_status(db_path, job_id, "failed")

    def process_scores(job_id: str) -> None:
        db_path = Path(".photobook-temp") / "project.db"
        cache_dir = Path(".photobook-temp") / "cache" / "models"
        update_job_status(db_path, job_id, "running")
        try:
            total = len(list_thumbnail_paths(db_path, 256))
            scored = score_thumbnails(db_path, cache_dir)
            update_job_progress(db_path, job_id, scored or total)
            update_job_status(db_path, job_id, "completed")
        except Exception:
            update_job_status(db_path, job_id, "failed")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/thumbnail")
    def thumbnail(path: str) -> FileResponse:
        cache_dir = (Path(".photobook-temp") / "cache" / "thumbnails").resolve()
        target = Path(path).resolve()
        if not str(target).startswith(str(cache_dir)):
            raise HTTPException(status_code=400, detail="Invalid thumbnail path")
        if not target.exists():
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        return FileResponse(target)

    @app.post("/api/ingest")
    def ingest(files: list[UploadFile] = File(...)) -> JSONResponse:
        project_root = Path(".photobook-temp")
        originals_dir = project_root / "uploads"
        db_path = project_root / "project.db"
        originals_dir.mkdir(parents=True, exist_ok=True)
        ensure_schema(db_path)

        stored_paths: list[Path] = []
        for upload in files:
            target_path = originals_dir / upload.filename
            with target_path.open("wb") as output:
                shutil.copyfileobj(upload.file, output)
            stored_paths.append(target_path)

        if not stored_paths:
            return JSONResponse({"error": "no files provided"}, status_code=400)

        job_id = uuid.uuid4().hex
        total = len(stored_paths) * 2
        create_job(db_path, job_id, "thumbnails", total)
        cluster_job_id = uuid.uuid4().hex
        create_job(db_path, cluster_job_id, "cluster", len(stored_paths))
        executor.submit(process_thumbnails, job_id, stored_paths, cluster_job_id)

        return JSONResponse(
            {
                "files": [str(path) for path in stored_paths],
                "job_id": job_id,
                "cluster_job_id": cluster_job_id,
            }
        )

    @app.get("/api/thumbnails")
    def thumbnails() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_thumbnails(db_path)})

    @app.get("/api/clusters")
    def clusters() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_clusters(db_path)})

    @app.get("/api/duplicates")
    def duplicates() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_duplicate_groups(db_path)})

    @app.post("/api/duplicates/ignore")
    def ignore_duplicate_group_api(payload: IgnoreGroupRequest) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        ignore_duplicate_group(db_path, payload.group_id)
        return JSONResponse({"status": "ok"})

    @app.post("/api/duplicates/ignore-photo")
    def ignore_duplicate_photo_api(payload: IgnorePhotoRequest) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        ignore_photo(db_path, payload.photo_path)
        return JSONResponse({"status": "ok"})

    @app.post("/api/duplicates/delete")
    def delete_duplicate_group_api(payload: DeleteGroupRequest) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        for photo_path in list_duplicate_photo_paths(db_path, payload.group_id):
            delete_photo_assets(db_path, photo_path)
        return JSONResponse({"status": "ok"})

    @app.post("/api/duplicates/delete-photo")
    def delete_duplicate_photo_api(payload: DeletePhotoRequest) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        delete_photo_assets(db_path, payload.photo_path)
        return JSONResponse({"status": "ok"})

    @app.post("/api/duplicates/resolve")
    def resolve_duplicate_group_api(payload: ResolveGroupRequest) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        set_duplicate_group_resolved(db_path, payload.group_id, payload.resolved)
        return JSONResponse({"status": "ok"})

    @app.get("/api/scores")
    def scores() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_photo_scores(db_path)})

    @app.get("/api/chapters")
    def chapters() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_chapters(db_path)})

    @app.post("/api/chapters")
    def create_chapter_api(payload: ChapterCreate) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        chapter_id = create_chapter(db_path, payload.name, payload.page_count)
        return JSONResponse({"id": chapter_id})

    @app.patch("/api/chapters/{chapter_id}")
    def update_chapter_api(chapter_id: int, payload: ChapterUpdate) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        update_chapter(db_path, chapter_id, name=payload.name)
        return JSONResponse({"status": "ok"})

    @app.post("/api/chapters/reorder")
    def reorder_chapters_api(payload: ChapterReorder) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        reorder_chapters(db_path, payload.chapter_ids)
        return JSONResponse({"status": "ok"})

    @app.post("/api/chapters/{chapter_id}/pages")
    def update_pages_api(chapter_id: int, payload: ChapterPagesUpdate) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        sync_pages_for_chapter(db_path, chapter_id, payload.page_count)
        return JSONResponse({"status": "ok"})

    @app.get("/api/chapters/{chapter_id}/pages")
    def list_pages_api(chapter_id: int) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_pages(db_path, chapter_id)})

    @app.get("/api/pages/{page_id}/items")
    def list_page_items_api(page_id: int) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_page_items(db_path, page_id)})

    @app.post("/api/pages/{page_id}/items")
    def create_page_item_api(page_id: int, payload: PageItemCreate) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        item_id = create_page_item(
            db_path,
            page_id,
            payload.item_type,
            payload.photo_path,
            payload.text,
            payload.x,
            payload.y,
            payload.w,
            payload.h,
            payload.z,
        )
        return JSONResponse({"id": item_id})

    @app.patch("/api/pages/items/{item_id}")
    def update_page_item_api(item_id: int, payload: PageItemUpdate) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        update_page_item(
            db_path,
            item_id,
            x=payload.x,
            y=payload.y,
            w=payload.w,
            h=payload.h,
            z=payload.z,
            text=payload.text,
            photo_path=payload.photo_path,
        )
        return JSONResponse({"status": "ok"})

    @app.post("/api/export")
    def export_book(payload: ExportRequest | None = None) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        chapters = list_chapters(db_path)
        selected_ids = (
            set(payload.chapter_ids) if payload and payload.chapter_ids else None
        )
        export_chapters = [
            chapter
            for chapter in chapters
            if not selected_ids or chapter["id"] in selected_ids
        ]
        export_payload = []
        for chapter in export_chapters:
            pages = list_pages_with_items(db_path, int(chapter["id"]))
            export_payload.append(
                {
                    "id": chapter["id"],
                    "name": chapter["name"],
                    "order_index": chapter["order_index"],
                    "page_count": chapter["page_count"],
                    "pages": pages,
                }
            )
        return JSONResponse({"chapters": export_payload})

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        job = get_job(db_path, job_id)
        if not job:
            return JSONResponse({"error": "job not found"}, status_code=404)
        return JSONResponse(job)

    @app.post("/api/cluster")
    def cluster_job() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        total = len(list_photo_paths(db_path))
        job_id = uuid.uuid4().hex
        create_job(db_path, job_id, "cluster", total)
        executor.submit(process_clusters, job_id)
        return JSONResponse({"job_id": job_id})

    @app.post("/api/dedupe")
    def dedupe_job() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        total = len(list_thumbnail_paths(db_path, 256))
        job_id = uuid.uuid4().hex
        create_job(db_path, job_id, "dedupe", total)
        executor.submit(process_dedupe, job_id)
        return JSONResponse({"job_id": job_id})

    @app.post("/api/score")
    def score_job() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        total = len(list_thumbnail_paths(db_path, 256))
        job_id = uuid.uuid4().hex
        create_job(db_path, job_id, "score", total)
        executor.submit(process_scores, job_id)
        return JSONResponse({"job_id": job_id})

    return app
