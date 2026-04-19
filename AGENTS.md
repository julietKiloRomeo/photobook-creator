# Agent Workflow

We work in tracked steps (`step-1.md`, `step-2.md`, etc.).
- The current step is the smallest numbered step that is not marked "(Completed)".
- Update the current step file as work is completed.
- Mark completion by adding "(Completed)" to the step title.

## Roles and Routing

Each agent only pulls GitHub issues labeled for its role and assigned to it.

- **Frontend Test Agent** (`role:test`): Runs frontend tests, captures screenshots, performs LLM visual inspection, and posts a report with recommendations to the GitHub issue. Uses `.agents/skills/webapp-testing`.
- **Developer Agent** (`role:dev`): Implements tasks from GitHub issues. Prefers simple over complex, small focused files, and changes that are easy for humans to review. Uses `.agents/skills/frontend-design` when doing UI work.
- **Refactor Agent** (`role:refactor`): Audits docstrings, README, and architecture. Opens issues/tasks to simplify structure and tests. Avoids special cases and prefers fail-fast behavior.
- **Project Manager Agent** (`role:pm`): Triages and assigns issues, manages labels, breaks large or vague requests into small well-scoped issues, and coordinates handoff to `merge-integrator` for merge/cleanup.

## Subagents

- Project subagent registration lives in `.codex/config.toml`.
- Subagent definitions live in `.codex/agents/*.toml` with per-role instruction files in `.codex/agents/*.md`.
- Role names:
  - `pm-agent`
  - `dev-agent`
  - `frontend-test-agent`
  - `refactor-agent`
  - `merge-integrator`
  - `docs-maintainer`
- Selection quick guide:
  - `pm-agent`: triage, issue decomposition, assignment/routing, and worktree orchestration.
  - `dev-agent`: implementation work in delegated worktrees.
  - `frontend-test-agent`: frontend test runs, screenshots, and issue-level validation reports.
  - `refactor-agent`: simplification and fail-fast refactors.
  - `merge-integrator`: validation, squash merge into `main`, and delegated worktree cleanup.
  - `docs-maintainer`: README/AGENTS/doc alignment with implemented behavior.
- Keep this `AGENTS.md` focused on shared project policy and keep role behavior in the subagent files.
- When role behavior changes, update matching files under `.codex/agents/`.

## GitHub-Only Communication

- All reports, recommendations, and cross-agent communication happen on GitHub issues.
- Do not create local report files.
- Use `.agents/skills/github-ops/scripts/` helpers for issue filtering and updates.
- Manually created issues enter the workflow once labeled and assigned to a role.

## Worktree Workflow

- Always sync from local `main` before starting work.
- Each role uses a separate git worktree and branch.
- Branch naming: `role/<issue-id>-<short-slug>`.
- Worktree path: `../photo-book-creator-wt/<role>/<issue-id>-<short-slug>`.
- Project Manager may create worktrees for agents; `merge-integrator` owns merge execution and cleanup.
- Use `.agents/skills/github-ops/scripts/worktree-create` and `worktree-cleanup` for consistent setup/teardown.

## UI/UX Specs

- **Look**: Flat surfaces, minimal borders, strong typography, ample whitespace.
- **Feel**: Guided and calm, with deliberate motion and clear hierarchy.
- **Preference**: Simple over complex; avoid special cases; fail fast.
- **Reviewability**: Small, focused files and minimal diffs whenever possible.

## Installed Skills

- `.agents/skills/frontend-design`
- `.agents/skills/webapp-testing`
- `.agents/skills/github-ops`
- `.agents/skills/using-git-worktrees`
- `.agents/skills/dispatching-parallel-agents`

## LLM Structured Output Policy

- For any production LLM integration that returns machine-readable data, use strict Structured Outputs with an explicit schema.
- Prefer typed schema models (Pydantic) and validate responses before applying side effects.
- Always handle refusal / schema-parse failure explicitly with a safe fallback path.
- Do not rely on free-form JSON parsing for core clustering or workflow decisions.

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

## Tooling Requirements

- `gh` (GitHub CLI) for issue workflows and `.agents/skills/github-ops/scripts/*`.
- `podman` to run the trufflehog secrets scan.
- `uv` for Python dependency management and running `ruff`.
- `node` + `npm` for frontend lint/test tasks.
