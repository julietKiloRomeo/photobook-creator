"""FastAPI app factory.

Routers are mounted under ``/api/*`` and attached in sub-step 1.3 onward.
The factory itself stays tiny so tests can spin up isolated app
instances without leaking process state.
"""

from __future__ import annotations

from fastapi import FastAPI

from shoebox import __version__
from shoebox.api import projects as projects_router
from shoebox.api import uploads as uploads_router
from shoebox.store import initialise


def create_app() -> FastAPI:
    app = FastAPI(title="shoebox", version=__version__)
    initialise()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(projects_router.router)
    app.include_router(uploads_router.router)

    return app
