---
name: github-ops
description: Project-specific GitHub workflow for issue triage, role routing, worktrees, and reporting. Use this skill whenever interacting with issues, labels, or worktrees.
license: MIT (see LICENSE.txt)
---

# GitHub Ops

This skill defines the GitHub-first workflow for this repo. All work is routed through issues and labels; all communication and reports happen in GitHub issues.

## Principles

- GitHub is the source of truth for tasks, updates, and reports.
- Prefer simple over complex. Keep changes small and easy to review.
- Fail fast. Avoid overly complicated control flow and special cases.

## Issue Routing

Use labels to route work:

- `role:dev` -> Developer Agent
- `role:test` -> Frontend Test Agent
- `role:refactor` -> Refactor Agent
- `role:pm` -> Project Manager Agent

Each agent only pulls issues with its role label and assigned to it.

## Worktrees

- Always sync from local `main` before starting work.
- Each role works in a separate git worktree and branch.
- Branch naming: `role/<issue-id>-<short-slug>`
- Worktree path: `../photo-book-creator-wt/<role>/<issue-id>-<short-slug>`
- Project Manager merges worktree branches and pushes to origin/GitHub.

## Reporting

- Do not create local report files.
- Post results, screenshots, and recommendations directly on the GitHub issue.
- Use issue comments for updates and decisions.

## Scripts

Use the scripts in `scripts/` to find assigned issues and post updates.

- `worktree-create <issue-id> <role> <short-slug>`: create a role worktree.
- `worktree-cleanup <worktree-path>`: remove a worktree and prune.
