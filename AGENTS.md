# Agent Workflow

We work in tracked steps (`step-1.md`, `step-2.md`, etc.).
- The current step is the smallest numbered step that is not marked "(Completed)".
- Update the current step file as work is completed.
- Mark completion by adding "(Completed)" to the step title.

## Python Environment Policy

Use `uv` for all Python dependency and environment management.
- Prefer `uv sync`, `uv run`, and `uv pip` commands.
- Do NOT manually create or activate virtual environments (`python -m venv`, `source .venv/bin/activate`) unless explicitly requested.
- Treat manual venv creation/activation as discouraged and avoid suggesting it in guidance.

Before any commit or push, run these checks from the repo root.

## 1) Secrets scan (trufflehog via podman)

```bash
podman run --rm -v "$PWD:/repo" -v "$PWD/.trufflehog:/tmp" docker.io/trufflesecurity/trufflehog:latest filesystem /repo
```

## 2) Tests

If this project has a test command, run it here. If no tests are configured yet, add the command below when it becomes available.

```bash
# Example (replace with real command)
<test-command>
```
