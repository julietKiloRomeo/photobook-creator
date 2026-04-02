#!/usr/bin/env bash
set -euo pipefail

root_dir="$(git rev-parse --show-toplevel)"
cd "$root_dir"

if ! command -v podman >/dev/null 2>&1; then
  echo "podman not found. Install podman to run trufflehog." >&2
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install uv to run ruff." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js to run frontend lint." >&2
  exit 1
fi

echo "Running secrets scan (trufflehog)"
podman run --rm -v "$PWD:/repo" -v "$PWD/.trufflehog:/tmp" docker.io/trufflesecurity/trufflehog:latest filesystem /repo

echo "Running ruff (uv)"
uv run ruff check .

if [ -f "$root_dir/ui/package.json" ]; then
  echo "Running frontend lint"
  (cd "$root_dir/ui" && npm run lint)
else
  echo "ui/package.json not found; skipping frontend lint."
fi
