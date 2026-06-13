"""Book router: auto-build and export."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from shoebox.pipeline.autobuild import auto_build
from shoebox.pipeline.export import build_export_bundle
from shoebox.store import connection, dao

router = APIRouter(tags=["book"])


@router.post("/api/projects/{project_id}/book/auto-build")
def auto_build_project_book(project_id: str) -> dict:
    with connection() as conn:
        if dao.get_project(conn, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
    return auto_build(project_id)


@router.post("/api/projects/{project_id}/export")
def export_project(project_id: str) -> Response:
    try:
        payload, filename = build_export_bundle(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=payload, media_type="application/zip", headers=headers)
