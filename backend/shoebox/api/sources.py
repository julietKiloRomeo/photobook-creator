"""Upload-batch provenance.

A source records that a batch of files was offered to a project. The
uploader creates one before it starts and passes its id on every chunk,
so a batch split across many requests stays one batch — which is what
makes "retry the rest of this import" and "undo this import"
answerable.

Only the expectation (``expected_file_count``) is stored. What actually
landed is counted from ``references_`` on read, so there is no
denormalised tally that can drift out of date.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from shoebox.api.schemas import Source, SourceCreate
from shoebox.store import connection, dao

router = APIRouter(prefix="/api/projects/{project_id}/sources", tags=["sources"])


@router.post("", response_model=Source, status_code=201)
def create_source(project_id: str, payload: SourceCreate) -> Source:
    with connection() as conn:
        if dao.get_project(conn, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        source = dao.create_source(
            conn,
            project_id=project_id,
            kind="upload",
            expected_file_count=payload.expected_file_count,
        )
    return Source.model_validate(source)


@router.get("", response_model=list[Source])
def list_sources(project_id: str) -> list[Source]:
    with connection() as conn:
        if dao.get_project(conn, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        sources = dao.list_sources(conn, project_id)
    return [Source.model_validate(s) for s in sources]
