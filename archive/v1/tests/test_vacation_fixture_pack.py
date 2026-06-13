from __future__ import annotations

import json
from pathlib import Path


def test_vacation_fixture_pack_manifest_and_files() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture_dir = root / "tests" / "fixtures" / "vacation-20"
    manifest_path = fixture_dir / "manifest.json"

    assert manifest_path.exists(), "Fixture manifest is missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["dataset"] == "vacation-20"
    assert manifest["count"] == 20
    items = manifest["items"]
    assert len(items) == 20

    for item in items:
        file_name = item["file"]
        assert file_name.endswith(".jpg")
        assert (fixture_dir / file_name).exists(), f"Missing fixture image: {file_name}"

