from __future__ import annotations

import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from photobook.project_store import (
    create_job,
    ensure_schema,
    get_job,
    list_clusters,
    list_duplicate_groups,
    list_photo_paths,
    list_thumbnail_paths,
    list_thumbnails,
    update_job_progress,
    update_job_status,
    upsert_thumbnail_records,
)
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
            cluster_count = cluster_photos_by_time(db_path)
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

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    return app
