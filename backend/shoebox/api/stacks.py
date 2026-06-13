"""Stacks router."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from shoebox.api.schemas import Stack, StackUpdate
from shoebox.store import connection, dao

router = APIRouter(tags=["stacks"])


def _to_stack(row: dict) -> Stack:
    return Stack(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        picked_reference_id=row.get("picked_reference_id"),
        reference_ids=row.get("reference_ids", []),
    )


@router.get("/api/projects/{project_id}/stacks", response_model=list[Stack])
def list_project_stacks(
    project_id: str,
    status: Literal["pending", "resolved", "ignored"] | None = Query(default=None),
) -> list[Stack]:
    with connection() as conn:
        rows = dao.list_stacks(conn, project_id, status=status)
    return [_to_stack(r) for r in rows]


@router.patch("/api/stacks/{stack_id}", response_model=Stack)
def update_stack(stack_id: str, payload: StackUpdate) -> Stack:
    with connection() as conn:
        existing = dao.get_stack(conn, stack_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Stack not found")
        # If a pick was supplied but no explicit status, treat it as resolved.
        next_status = payload.status
        if payload.picked_reference_id is not None and next_status is None:
            next_status = "resolved"
        updated = dao.update_stack(
            conn,
            stack_id,
            picked_reference_id=payload.picked_reference_id,
            status=next_status,
        )
    assert updated is not None
    return _to_stack(updated)
