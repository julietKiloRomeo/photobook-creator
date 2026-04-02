# Spec Review Task 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update README.md to the provided content and remove legacy spec/story docs.

**Architecture:** Documentation-only changes in the repo root. Replace README content wholesale, then delete legacy spec/story docs to avoid drift.

**Tech Stack:** Markdown, git

---

## File Map

- Modify: `README.md`
- Delete: `SPECS.md`
- Delete: `STORIES.md`

### Task 1: Gather the provided README content

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate provided README content source**

Check the spec/issue artifacts for the full README replacement text and screenshot references.

- [ ] **Step 2: Open current README for reference**

```bash
sed -n '1,200p' README.md
```

Expected: current README content printed to stdout.

### Task 2: Replace README.md with provided content

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Overwrite README.md with the provided content**

Paste the provided README content verbatim, ensuring the screenshots section and updated instructions are preserved as given.

- [ ] **Step 2: Verify README renders correctly**

```bash
sed -n '1,200p' README.md
```

Expected: updated README content printed to stdout with the screenshots section present.

### Task 3: Remove legacy spec/story docs

**Files:**
- Delete: `SPECS.md`
- Delete: `STORIES.md`

- [ ] **Step 1: Confirm legacy files exist before removal**

```bash
ls SPECS.md STORIES.md
```

Expected: both files listed, or a clear error if already removed.

- [ ] **Step 2: Remove legacy docs from git**

```bash
git rm SPECS.md STORIES.md
```

Expected: output similar to `rm 'SPECS.md'` and `rm 'STORIES.md'`.

### Task 4: Sanity check and stage changes

**Files:**
- Modify: `README.md`
- Delete: `SPECS.md`
- Delete: `STORIES.md`

- [ ] **Step 1: Review git status**

```bash
git status -sb
```

Expected: README.md modified and SPECS.md/STORIES.md deleted.

- [ ] **Step 2: Stage README if needed**

```bash
git add README.md
```

Expected: no output; README staged.
