"""Smoke tests for the sub-step 1.1 scaffolding.

These assert *intent only*:
- the app boots and reports it's healthy;
- the vacation-20 fixture pack is present and complete.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_health_endpoint_reports_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body.get("version"), str)


def test_vacation_fixture_pack_is_complete(fixture_pack_dir: Path) -> None:
    manifest_path = fixture_pack_dir / "manifest.json"
    assert manifest_path.exists(), "vacation-20 manifest missing"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest["items"]
    assert len(items) == 20

    for item in items:
        assert (fixture_pack_dir / item["file"]).exists()
