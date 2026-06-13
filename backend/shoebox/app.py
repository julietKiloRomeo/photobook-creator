"""FastAPI app factory.

Routers are mounted under ``/api/*`` and attached in sub-step 1.3 onward.
The factory itself stays tiny so tests can spin up isolated app
instances without leaking process state.
"""

from __future__ import annotations

from fastapi import FastAPI

from shoebox import __version__
from shoebox.api import jobs as jobs_router
from shoebox.api import projects as projects_router
from shoebox.api import stacks as stacks_router
from shoebox.api import themes as themes_router
from shoebox.api import uploads as uploads_router
from shoebox.jobs import get_runner
from shoebox.pipeline.jobs import process_project
from shoebox.store import initialise


def create_app() -> FastAPI:
    app = FastAPI(title="shoebox", version=__version__)
    initialise()

    runner = get_runner()
    runner.register("process", process_project)
    runner.start()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(projects_router.router)
    app.include_router(uploads_router.router)
    app.include_router(stacks_router.router)
    app.include_router(themes_router.router)
    app.include_router(jobs_router.router)

    return app
