"""Pages + page-items router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from shoebox.api.schemas import (
    Page,
    PageCreate,
    PageItem,
    PageItemCreate,
    PageItemUpdate,
    PageUpdate,
)
from shoebox.store import connection, dao

router = APIRouter(tags=["pages"])


def _to_page(row: dict) -> Page:
    return Page(
        id=row["id"],
        theme_id=row["theme_id"],
        order_index=row["order_index"],
        layout_id=row["layout_id"],
    )


def _to_item(row: dict) -> PageItem:
    return PageItem(
        id=row["id"],
        page_id=row["page_id"],
        kind=row["kind"],
        reference_id=row.get("reference_id"),
        text_content=row.get("text_content"),
        slot_index=row["slot_index"],
        position_json=row.get("position_json") or "{}",
    )


@router.get("/api/themes/{theme_id}/pages", response_model=list[Page])
def list_theme_pages(theme_id: str) -> list[Page]:
    with connection() as conn:
        if dao.get_theme(conn, theme_id) is None:
            raise HTTPException(status_code=404, detail="Theme not found")
        return [_to_page(p) for p in dao.list_pages(conn, theme_id)]


@router.post("/api/themes/{theme_id}/pages", response_model=Page, status_code=201)
def create_theme_page(theme_id: str, payload: PageCreate) -> Page:
    with connection() as conn:
        if dao.get_theme(conn, theme_id) is None:
            raise HTTPException(status_code=404, detail="Theme not found")
        page = dao.create_page(conn, theme_id=theme_id, layout_id=payload.layout_id)
    return _to_page(page)


@router.patch("/api/pages/{page_id}", response_model=Page)
def update_page(page_id: str, payload: PageUpdate) -> Page:
    with connection() as conn:
        if dao.get_page(conn, page_id) is None:
            raise HTTPException(status_code=404, detail="Page not found")
        updated = dao.update_page(
            conn, page_id, layout_id=payload.layout_id, order_index=payload.order_index
        )
    assert updated is not None
    return _to_page(updated)


@router.delete("/api/pages/{page_id}", status_code=204)
def delete_page(page_id: str) -> None:
    """Delete a page and its items; remaining pages close the order gap."""
    with connection() as conn:
        if not dao.delete_page(conn, page_id):
            raise HTTPException(status_code=404, detail="Page not found")


@router.get("/api/pages/{page_id}/items", response_model=list[PageItem])
def list_page_items(page_id: str) -> list[PageItem]:
    with connection() as conn:
        if dao.get_page(conn, page_id) is None:
            raise HTTPException(status_code=404, detail="Page not found")
        return [_to_item(it) for it in dao.list_page_items(conn, page_id)]


@router.post("/api/pages/{page_id}/items", response_model=PageItem, status_code=201)
def add_page_item(page_id: str, payload: PageItemCreate) -> PageItem:
    with connection() as conn:
        if dao.get_page(conn, page_id) is None:
            raise HTTPException(status_code=404, detail="Page not found")
        try:
            item = dao.add_page_item(
                conn,
                page_id=page_id,
                kind=payload.kind,
                slot_index=payload.slot_index,
                reference_id=payload.reference_id,
                text_content=payload.text_content,
                position_json=payload.position_json,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_item(item)


@router.patch("/api/page-items/{item_id}", response_model=PageItem)
def update_page_item(item_id: str, payload: PageItemUpdate) -> PageItem:
    with connection() as conn:
        if dao.get_page_item(conn, item_id) is None:
            raise HTTPException(status_code=404, detail="Page item not found")
        updated = dao.update_page_item(
            conn,
            item_id,
            reference_id=payload.reference_id,
            text_content=payload.text_content,
            slot_index=payload.slot_index,
            position_json=payload.position_json,
        )
    assert updated is not None
    return _to_item(updated)


@router.delete("/api/page-items/{item_id}", status_code=204)
def delete_page_item(item_id: str) -> None:
    with connection() as conn:
        if not dao.delete_page_item(conn, item_id):
            raise HTTPException(status_code=404, detail="Page item not found")
