"""FastAPI app factory.

Routers are mounted under ``/api/*`` and attached in sub-step 1.3 onward.
The factory itself stays tiny so tests can spin up isolated app
instances without leaking process state.
"""

from __future__ import annotations

from fastapi import FastAPI

from shoebox import __version__


def create_app() -> FastAPI:
    app = FastAPI(title="shoebox", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
