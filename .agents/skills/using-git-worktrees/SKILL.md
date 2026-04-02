---
name: using-git-worktrees
description: Worktree workflows for parallel development and clean branch isolation.
license: Apache-2.0 (see LICENSE.txt)
---

# Using Git Worktrees

Prefer `git worktree` for parallel feature work. Each role uses a separate worktree and branch.

## Basic Flow

1. Sync local `main`.
2. Create a worktree for the role and issue.
3. Work and commit in the worktree.
4. Merge via Project Manager.

## Common Commands

- `git worktree add -b role/<issue-id>-<slug> ../photo-book-creator-wt/<role>/<issue-id>-<slug> main`
- `git worktree list`
- `git worktree remove ../photo-book-creator-wt/<role>/<issue-id>-<slug>`
- `git worktree prune`
