"""Uploads + reference image serving.

Each uploaded file goes through tier-1 synchronously:
  bytes → SHA-256 → save original → EXIF + pHash + thumbnails → upsert.

Originals live at ``data/projects/<id>/originals/<file_hash>.<ext>``.
Derivatives at ``thumbs/`` and ``medium/`` next to originals.

If the same bytes are uploaded twice in the same project, the second
upload returns the existing reference and is counted as a duplicate.
The file isn't written a second time.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from shoebox.api.schemas import Reference, UploadResult
from shoebox.config import get_settings
from shoebox.pipeline.tier1 import ingest_file
from shoebox.store import connection, dao

router = APIRouter(tags=["uploads"])


def _to_reference(row: dict) -> Reference:
    return Reference(
        id=row["id"],
        project_id=row["project_id"],
        file_hash=row["file_hash"],
        captured_at=row.get("captured_at"),
        width=row.get("width"),
        height=row.get("height"),
        uploaded_at=row["uploaded_at"],
    )


def _ext_for(filename: str | None) -> str:
    if not filename:
        return ".jpg"
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else ".jpg"


@router.post(
    "/api/projects/{project_id}/uploads",
    response_model=UploadResult,
    status_code=201,
)
async def upload_files(project_id: str, files: list[UploadFile]) -> UploadResult:
    settings = get_settings()
    with connection() as conn:
        project = dao.get_project(conn, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    originals_dir = settings.project_originals_dir(project_id)
    thumbs_dir = settings.project_thumbs_dir(project_id)
    medium_dir = settings.project_medium_dir(project_id)
    originals_dir.mkdir(parents=True, exist_ok=True)

    accepted_refs: list[dict] = []
    duplicates = 0

    for upload in files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=_ext_for(upload.filename)) as tmp:
            tmp_path = Path(tmp.name)
            content = await upload.read()
            tmp.write(content)
        try:
            result = ingest_file(
                source_path=tmp_path,
                thumbs_dir=thumbs_dir,
                medium_dir=medium_dir,
                thumb_small_width=settings.thumb_small_width,
                thumb_medium_width=settings.thumb_medium_width,
            )
            final_path = originals_dir / f"{result.file_hash}{_ext_for(upload.filename)}"
            is_new_on_disk = not final_path.exists()
            if is_new_on_disk:
                shutil.move(str(tmp_path), final_path)

            with connection() as conn:
                already_known = dao.get_reference(conn, _find_existing_id(conn, project_id, result.file_hash) or "") is not None
                ref = dao.upsert_reference(
                    conn,
                    project_id=project_id,
                    original_path=str(final_path),
                    file_hash=result.file_hash,
                    phash=result.phash,
                    captured_at=result.captured_at,
                    gps_lat=result.gps_lat,
                    gps_lon=result.gps_lon,
                    width=result.width,
                    height=result.height,
                )
                if already_known:
                    duplicates += 1
                else:
                    accepted_refs.append(ref)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    return UploadResult(
        accepted=len(accepted_refs),
        duplicates=duplicates,
        references=[_to_reference(r) for r in accepted_refs],
    )


def _find_existing_id(conn, project_id: str, file_hash: str) -> str | None:
    cur = conn.execute(
        "SELECT id FROM references_ WHERE project_id = ? AND file_hash = ?",
        (project_id, file_hash),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def _serve(project_id: str, reference_id: str, kind: str) -> FileResponse:
    settings = get_settings()
    with connection() as conn:
        ref = dao.get_reference(conn, reference_id)
    if ref is None or ref["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Reference not found")

    file_hash = ref["file_hash"]
    if kind == "thumb":
        path = settings.project_thumbs_dir(project_id) / f"{file_hash}.jpg"
    elif kind == "medium":
        path = settings.project_medium_dir(project_id) / f"{file_hash}.jpg"
    elif kind == "original":
        path = Path(ref["original_path"])
    else:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Unknown derivative kind")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not available")
    return FileResponse(path)


@router.get("/api/projects/{project_id}/references/{reference_id}/thumb")
def get_reference_thumb(project_id: str, reference_id: str) -> FileResponse:
    return _serve(project_id, reference_id, "thumb")


@router.get("/api/projects/{project_id}/references/{reference_id}/medium")
def get_reference_medium(project_id: str, reference_id: str) -> FileResponse:
    return _serve(project_id, reference_id, "medium")


@router.get("/api/projects/{project_id}/references/{reference_id}/original")
def get_reference_original(project_id: str, reference_id: str) -> FileResponse:
    return _serve(project_id, reference_id, "original")
