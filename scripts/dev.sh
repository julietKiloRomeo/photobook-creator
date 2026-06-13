#!/usr/bin/env bash
# Run the FastAPI backend and the Vite frontend together for development.
# Backend on :8000, frontend on :5173 (Vite proxies /api → :8000).
set -euo pipefail

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run shoebox-api --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
