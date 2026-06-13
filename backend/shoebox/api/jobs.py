"""Jobs router: kick off processing, poll status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from shoebox.api.schemas import Job
from shoebox.jobs import get_runner
from shoebox.store import connection, dao

router = APIRouter(tags=["jobs"])


def _to_job(row: dict) -> Job:
    return Job(
        id=row["id"],
        project_id=row["project_id"],
        kind=row["kind"],
        status=row["status"],
        progress=row["progress"],
        message=row.get("message"),
        error=row.get("error"),
    )


@router.post("/api/projects/{project_id}/process", response_model=Job, status_code=202)
def process_project(project_id: str) -> Job:
    with connection() as conn:
        if dao.get_project(conn, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
    job = get_runner().enqueue(project_id=project_id, kind="process")
    return _to_job(job)


@router.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    with connection() as conn:
        job = dao.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job(job)
