"""Themes router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from shoebox.api.schemas import Theme, ThemeAssignment, ThemeCreate, ThemeUpdate
from shoebox.store import connection, dao

router = APIRouter(tags=["themes"])


def _to_theme(row: dict) -> Theme:
    return Theme(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        color=row["color"],
        order_index=row["order_index"],
        ai_proposed=bool(row["ai_proposed"]),
    )


@router.get("/api/projects/{project_id}/themes", response_model=list[Theme])
def list_project_themes(project_id: str) -> list[Theme]:
    with connection() as conn:
        return [_to_theme(t) for t in dao.list_themes(conn, project_id)]


@router.post("/api/projects/{project_id}/themes", response_model=Theme, status_code=201)
def create_project_theme(project_id: str, payload: ThemeCreate) -> Theme:
    with connection() as conn:
        if dao.get_project(conn, project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        theme = dao.create_theme(
            conn,
            project_id=project_id,
            name=payload.name,
            color=payload.color or "#4a44c2",
        )
    return _to_theme(theme)


@router.patch("/api/themes/{theme_id}", response_model=Theme)
def update_theme(theme_id: str, payload: ThemeUpdate) -> Theme:
    with connection() as conn:
        existing = dao.get_theme(conn, theme_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Theme not found")
        updated = dao.update_theme(
            conn,
            theme_id,
            name=payload.name,
            color=payload.color,
            order_index=payload.order_index,
        )
    assert updated is not None
    return _to_theme(updated)


@router.post("/api/themes/{theme_id}/assign", status_code=204)
def assign_stack(theme_id: str, payload: ThemeAssignment) -> None:
    with connection() as conn:
        if dao.get_theme(conn, theme_id) is None:
            raise HTTPException(status_code=404, detail="Theme not found")
        if dao.get_stack(conn, payload.stack_id) is None:
            raise HTTPException(status_code=404, detail="Stack not found")
        dao.assign_stack_to_theme(conn, stack_id=payload.stack_id, theme_id=theme_id)


@router.get("/api/themes/{theme_id}/stacks", response_model=list[str])
def list_theme_stack_ids(theme_id: str) -> list[str]:
    with connection() as conn:
        if dao.get_theme(conn, theme_id) is None:
            raise HTTPException(status_code=404, detail="Theme not found")
        return dao.list_stack_ids_for_theme(conn, theme_id)
