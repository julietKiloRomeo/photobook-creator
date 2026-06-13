"""In-process background job runner.

A single ``Worker`` thread pulls jobs out of a queue and runs them
sequentially. State is mirrored to the ``jobs`` SQLite table so the API
can poll progress.

This is deliberately *not* Celery / RQ / arq: shoebox runs on a family
laptop or a mini-PC, and the only background work is the tier-2
pipeline. A 100-line thread + queue handles it.

Each project effectively gets its own job lane because we key jobs by
project_id and the worker processes them in FIFO order; if two
processes for the same project queue, the second waits.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any

from shoebox.store import connection, dao

JobFunc = Callable[[str, "JobReporter"], None]


class JobReporter:
    """Handle passed to job functions for reporting progress."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def progress(self, value: float, message: str | None = None) -> None:
        with connection() as conn:
            dao.update_job(conn, self.job_id, progress=value, message=message)


class JobRunner:
    """Spawns a worker thread that processes queued jobs."""

    def __init__(self, handlers: dict[str, JobFunc] | None = None) -> None:
        self._queue: Queue[tuple[str, str]] = Queue()
        self._handlers: dict[str, JobFunc] = dict(handlers or {})
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def register(self, kind: str, func: JobFunc) -> None:
        self._handlers[kind] = func

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="shoebox-jobs", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def enqueue(self, *, project_id: str, kind: str) -> dict[str, Any]:
        if kind not in self._handlers:
            raise ValueError(f"No handler registered for job kind: {kind!r}")
        with connection() as conn:
            job = dao.create_job(conn, project_id=project_id, kind=kind)
        self._queue.put((job["id"], kind))
        self.start()
        return job

    def wait_idle(self, timeout: float = 30.0) -> None:
        """Block until the queue is empty and the worker is idle. Test helper."""
        deadline = threading.Event()

        def _trip() -> None:
            deadline.set()

        timer = threading.Timer(timeout, _trip)
        timer.daemon = True
        timer.start()
        try:
            while not deadline.is_set():
                if self._queue.empty() and not self._busy:
                    return
                deadline.wait(timeout=0.05)
            raise TimeoutError("Jobs did not drain within timeout")
        finally:
            timer.cancel()

    # ----- internals -----

    _busy: bool = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id, kind = self._queue.get(timeout=0.1)
            except Empty:
                continue
            self._busy = True
            try:
                self._run_one(job_id, kind)
            finally:
                self._busy = False
                self._queue.task_done()

    def _run_one(self, job_id: str, kind: str) -> None:
        handler = self._handlers.get(kind)
        if handler is None:
            with connection() as conn:
                dao.update_job(
                    conn,
                    job_id,
                    status="failed",
                    error=f"No handler for {kind!r}",
                    finished=True,
                )
            return

        with connection() as conn:
            job = dao.get_job(conn, job_id)
            if job is None:
                return
            project_id = job["project_id"]
            dao.update_job(conn, job_id, status="running", started=True)

        reporter = JobReporter(job_id)
        try:
            handler(project_id, reporter)
        except Exception as exc:
            with connection() as conn:
                dao.update_job(
                    conn,
                    job_id,
                    status="failed",
                    error=str(exc),
                    finished=True,
                )
            return

        with connection() as conn:
            dao.update_job(conn, job_id, status="completed", progress=1.0, finished=True)


_runner: JobRunner | None = None
_runner_lock = threading.Lock()


def get_runner() -> JobRunner:
    """Module-level singleton; created lazily so tests can reset state."""
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = JobRunner()
        return _runner


def reset_runner() -> None:
    """Test hook: drop the singleton so the next call creates a fresh one."""
    global _runner
    with _runner_lock:
        if _runner is not None:
            _runner.stop()
        _runner = None
