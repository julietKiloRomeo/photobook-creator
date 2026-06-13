"""Projects router: list, create, get, delete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from shoebox.api.schemas import Project, ProjectCreate
from shoebox.store import connection, dao

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[Project])
def list_projects() -> list[Project]:
    with connection() as conn:
        return [Project.model_validate(p) for p in dao.list_projects(conn)]


@router.post("", response_model=Project, status_code=201)
def create_project(payload: ProjectCreate) -> Project:
    with connection() as conn:
        return Project.model_validate(dao.create_project(conn, name=payload.name))


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    with connection() as conn:
        project = dao.get_project(conn, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project.model_validate(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    with connection() as conn:
        deleted = dao.delete_project(conn, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
