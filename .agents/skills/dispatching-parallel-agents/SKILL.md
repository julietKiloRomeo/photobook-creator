---
name: dispatching-parallel-agents
description: Guidance for splitting work and dispatching parallel agents safely.
license: Apache-2.0 (see LICENSE.txt)
---

# Dispatching Parallel Agents

Use parallel agents when tasks can be isolated and do not require shared context.

## When to Dispatch

- Multiple independent investigations or experiments.
- Separate files or subsystems with minimal overlap.
- Parallel test runs or environment checks.

## Guardrails

- Avoid overlapping edits to the same files.
- Coordinate via GitHub issues and comments.
- Keep each agent scope small and well-defined.
