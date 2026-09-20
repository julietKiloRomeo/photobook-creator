"""Uploads + reference image serving.

Each uploaded file goes through tier-1 synchronously:
  bytes → staged EXIF + pHash + thumbnails → atomic persistence.

Originals live at ``data/projects/<id>/originals/<file_hash>.<ext>``.
Derivatives at ``thumbs/`` and ``medium/`` next to originals.

If the same bytes are uploaded twice in the same project, the second
upload returns the existing reference and is counted as a duplicate.
The file isn't written a second time.

Large batches arrive as several small requests so one mid-flight
failure cannot lose the whole batch. Such a client sends
``?defer_processing=true`` on every chunk and calls
``POST /api/projects/{id}/process`` once at the end, which keeps a
163-photo upload at exactly one tier-2 run instead of one per chunk.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from shoebox.api.schemas import Reference, UploadRejection, UploadResult
from shoebox.config import get_settings
from shoebox.jobs import get_runner
from shoebox.pipeline.tier1 import ImageDecodeError, ingest_file
from shoebox.store import connection, dao

log = logging.getLogger(__name__)

router = APIRouter(tags=["uploads"])

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}


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


def _safe_filename(filename: str | None) -> str:
    return Path((filename or "").replace("\\", "/")).name or "unnamed file"


def _move_if_missing(source: Path, target: Path, created_paths: list[Path]) -> None:
    if target.exists():
        return
    shutil.move(str(source), str(target))
    created_paths.append(target)


@router.post(
    "/api/projects/{project_id}/uploads",
    response_model=UploadResult,
    status_code=201,
)
async def upload_files(
    project_id: str,
    files: list[UploadFile],
    defer_processing: Annotated[bool, Query()] = False,
) -> UploadResult:
    settings = get_settings()
    with connection() as conn:
        project = dao.get_project(conn, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    project_dir = settings.project_dir(project_id)
    originals_dir = settings.project_originals_dir(project_id)
    thumbs_dir = settings.project_thumbs_dir(project_id)
    medium_dir = settings.project_medium_dir(project_id)
    for artifact_dir in (originals_dir, thumbs_dir, medium_dir):
        artifact_dir.mkdir(parents=True, exist_ok=True)

    accepted_refs: list[dict] = []
    duplicates = 0
    rejected: list[UploadRejection] = []

    def reject(filename: str, reason: str, detail: str = "") -> None:
        """Record a rejection.

        The response body carries only the coarse category — decoder
        output can echo file bytes back to the client. The full detail
        goes to the log, which is where jkr can actually diagnose why a
        photo did not make it in.
        """
        log.warning(
            "Upload rejected for project %s: %s — %s%s",
            project_id,
            filename,
            reason,
            f" [{detail}]" if detail else "",
        )
        rejected.append(UploadRejection(filename=filename, reason=reason))

    log.info("Upload of %d file(s) started for project %s", len(files), project_id)

    for upload in files:
        filename = _safe_filename(upload.filename)
        content = await upload.read()
        if not content:
            reject(filename, "file is empty")
            continue

        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            reject(
                filename,
                "unsupported file type",
                detail=f"extension={extension or 'none'}",
            )
            continue

        with tempfile.TemporaryDirectory(dir=project_dir, prefix=".upload-") as tmp:
            staging_dir = Path(tmp)
            source_path = staging_dir / f"source{extension}"
            source_path.write_bytes(content)
            staged_thumbs_dir = staging_dir / "thumbs"
            staged_medium_dir = staging_dir / "medium"
            try:
                result = ingest_file(
                    source_path=source_path,
                    thumbs_dir=staged_thumbs_dir,
                    medium_dir=staged_medium_dir,
                    thumb_small_width=settings.thumb_small_width,
                    thumb_medium_width=settings.thumb_medium_width,
                )
            except ImageDecodeError as exc:
                reject(filename, "file could not be decoded", detail=str(exc))
                continue

            final_original = originals_dir / f"{result.file_hash}{extension}"
            artifacts = (
                (source_path, final_original),
                (
                    staged_thumbs_dir / f"{result.file_hash}.jpg",
                    thumbs_dir / f"{result.file_hash}.jpg",
                ),
                (
                    staged_medium_dir / f"{result.file_hash}.jpg",
                    medium_dir / f"{result.file_hash}.jpg",
                ),
            )
            created_paths: list[Path] = []
            transaction_succeeded = False
            try:
                with connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    with conn:
                        ref, created = dao.insert_reference_if_new(
                            conn,
                            project_id=project_id,
                            original_path=str(final_original),
                            file_hash=result.file_hash,
                            phash=result.phash,
                            captured_at=result.captured_at,
                            gps_lat=result.gps_lat,
                            gps_lon=result.gps_lon,
                            width=result.width,
                            height=result.height,
                        )
                        if created:
                            for staged_path, final_path in artifacts:
                                _move_if_missing(
                                    staged_path, final_path, created_paths
                                )
                    transaction_succeeded = True
            finally:
                if not transaction_succeeded:
                    for path in reversed(created_paths):
                        path.unlink(missing_ok=True)

            if created:
                accepted_refs.append(ref)
            else:
                duplicates += 1

    job_id: str | None = None
    if accepted_refs and not defer_processing:
        job = get_runner().enqueue(project_id=project_id, kind="process")
        job_id = job["id"]

    log.info(
        "Upload finished for project %s: %d accepted, %d duplicate, %d rejected, job=%s",
        project_id,
        len(accepted_refs),
        duplicates,
        len(rejected),
        job_id,
    )

    return UploadResult(
        accepted=len(accepted_refs),
        duplicates=duplicates,
        references=[_to_reference(r) for r in accepted_refs],
        rejected=rejected,
        job_id=job_id,
    )


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
