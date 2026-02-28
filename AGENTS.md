# Agent Workflow

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

## 3) Sync the skill folder

Keep the OpenCode skill copy in sync when you change this repo. From the repo root:

```bash
rsync -a ./ /home/jkr/.config/opencode/skills/photo-book-creator/ --exclude .git/
```
