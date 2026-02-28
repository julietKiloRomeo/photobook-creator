from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from photobook.project_store import (
    ensure_schema,
    list_thumbnails,
    upsert_thumbnail_records,
)
from photobook.thumbnails import generate_thumbnails, to_thumbnail_record


def create_app() -> FastAPI:
    app = FastAPI(title="Photo Book Creator")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/ingest")
    def ingest(files: list[UploadFile] = File(...)) -> JSONResponse:
        project_root = Path(".photobook-temp")
        originals_dir = project_root / "uploads"
        cache_dir = project_root / "cache" / "thumbnails"
        db_path = project_root / "project.db"
        originals_dir.mkdir(parents=True, exist_ok=True)
        ensure_schema(db_path)

        stored_paths: list[Path] = []
        for upload in files:
            target_path = originals_dir / upload.filename
            with target_path.open("wb") as output:
                shutil.copyfileobj(upload.file, output)
            stored_paths.append(target_path)

        results = generate_thumbnails(stored_paths, cache_dir, [256, 1024])
        records = [to_thumbnail_record(result) for result in results]
        upsert_thumbnail_records(db_path, records)

        return JSONResponse(
            {
                "files": [str(path) for path in stored_paths],
                "thumbnails": records,
            }
        )

    @app.get("/api/thumbnails")
    def thumbnails() -> JSONResponse:
        db_path = Path(".photobook-temp") / "project.db"
        ensure_schema(db_path)
        return JSONResponse({"items": list_thumbnails(db_path)})

    return app
