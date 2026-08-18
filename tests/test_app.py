from pathlib import Path

from fastapi.testclient import TestClient
from shoebox.app import create_app
from shoebox.config import get_settings


def test_serves_static_frontend_without_shadowing_api(
    settings, tmp_path: Path, monkeypatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>shoebox</h1>")
    monkeypatch.setenv("SHOEBOX_STATIC_DIR", str(static_dir))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        assert client.get("/").text == "<h1>shoebox</h1>"
        assert client.get("/api/health").json()["status"] == "ok"
