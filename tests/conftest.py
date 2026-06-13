"""Shared pytest fixtures.

Each test gets an isolated ``data_dir`` so the real ``./data`` is never
touched. Tests should drive shoebox through the API, not poke internals.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shoebox.app import create_app
from shoebox.config import Settings, get_settings
from shoebox.jobs import reset_runner


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Settings pointed at an isolated tmp data dir, with the cache cleared."""
    monkeypatch.setenv("SHOEBOX_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    reset_runner()
    yield get_settings()
    reset_runner()
    get_settings.cache_clear()


@pytest.fixture()
def fixture_pack_dir() -> Path:
    """Path to the vacation-20 fixture pack (20 AI-generated photos)."""
    here = Path(__file__).resolve().parent
    return here / "fixtures" / "vacation-20"


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    return TestClient(create_app())
