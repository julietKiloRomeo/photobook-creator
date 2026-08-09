"""Pydantic schemas for the HTTP API.

These define the public contract. The DAO returns dicts; the routers
convert to these models for response serialisation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Project(BaseModel):
    id: str
    name: str
    created_at: str
    status: str
    photo_count: int


class Reference(BaseModel):
    id: str
    project_id: str
    file_hash: str
    captured_at: str | None
    width: int | None
    height: int | None
    uploaded_at: str


class UploadRejection(BaseModel):
    filename: str
    # Deliberately coarse: decoder output can echo raw file bytes, so it
    # never crosses the API boundary. Full detail lives in the log.
    reason: Literal[
        "unsupported file type",
        "file could not be decoded",
        "file is empty",
    ]


class UploadResult(BaseModel):
    accepted: int
    duplicates: int
    references: list[Reference]
    rejected: list[UploadRejection]
    job_id: str | None


class Stack(BaseModel):
    id: str
    project_id: str
    status: str
    picked_reference_id: str | None
    reference_ids: list[str]


class StackUpdate(BaseModel):
    picked_reference_id: str | None = None
    status: str | None = None


class Theme(BaseModel):
    id: str
    project_id: str
    name: str
    color: str
    order_index: int
    ai_proposed: bool


class ThemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = None


class ThemeUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    order_index: int | None = None


class ThemeAssignment(BaseModel):
    stack_id: str


class Page(BaseModel):
    id: str
    theme_id: str
    order_index: int
    layout_id: str


class PageCreate(BaseModel):
    layout_id: str = "grid-2x2"


class PageUpdate(BaseModel):
    layout_id: str | None = None
    order_index: int | None = None


class PageItem(BaseModel):
    id: str
    page_id: str
    kind: str
    reference_id: str | None
    text_content: str | None
    slot_index: int
    position_json: str


class PageItemCreate(BaseModel):
    kind: str
    slot_index: int = 0
    reference_id: str | None = None
    text_content: str | None = None
    position_json: str = "{}"


class PageItemUpdate(BaseModel):
    reference_id: str | None = None
    text_content: str | None = None
    slot_index: int | None = None
    position_json: str | None = None


class Job(BaseModel):
    id: str
    project_id: str
    kind: str
    status: str
    progress: float
    message: str | None
    error: str | None
