from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photobook.api import create_app


@pytest.mark.gate
def test_full_app_gate_canonical_journey(tmp_path, monkeypatch) -> None:
    """
    Strict gate suite:
    This intentionally fails until the full darkroom app behavior is implemented end-to-end.
    """

    db_path = tmp_path / "project.db"
    monkeypatch.setenv("PHOTOBOOK_DB_PATH", str(db_path))
    client = TestClient(create_app())

    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (root / "tests" / "fixtures" / "vacation-20" / "manifest.json").read_text(encoding="utf-8")
    )
    items = manifest["items"]

    seed_payload = {
        "items": [
            {
                "source": str((root / item["path"]).resolve()),
                "source_type": "path",
                "label": item["id"],
                "metadata": {
                    "tags": item["tags"],
                    "prompt": item["prompt"],
                    "seed": item.get("seed"),
                },
            }
            for item in items
        ]
    }

    seed = client.post("/api/intake/references", json=seed_payload)
    assert seed.status_code == 200
    assert len(seed.json()["items"]) == 20

    # Full-app required API surface (not implemented yet):
    required_endpoints = [
        ("GET", "/api/stacks"),
        ("POST", "/api/duel/pick"),
        ("GET", "/api/themes"),
        ("GET", "/api/timeline"),
        ("POST", "/api/book/auto-build"),
    ]

    missing = []
    for method, path in required_endpoints:
        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json={})
        if response.status_code in (404, 405):
            missing.append(path)

    assert not missing, (
        "Full-app gate failed: missing darkroom capabilities. "
        f"Implement endpoint(s): {', '.join(missing)}"
    )
