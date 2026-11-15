# CI — gating a merge on the human decision

`hunkgate ci <item>` exits 0 only when the gate is READY (every hunk
decided). It exits 2 otherwise. `--allow-review` also passes when only
REVIEW/OK hunks are undecided — useful when BLOCK is the only thing
that must never slip through.

## GitHub Actions

```yaml
name: agent-gate
on:
  pull_request:
    branches: [main]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install hunkgate
        run: python -m pip install -e .   # from source; no PyPI package yet
      - name: Capture the PR diff
        run: |
          hunkgate init
          git diff origin/main...HEAD > /tmp/pr.diff
          hunkgate capture /tmp/pr.diff --title "PR #${{ github.event.number }}"
      - name: Gate on the human decision
        run: |
          ITEM=$(hunkgate list | head -1 | awk '{print $1}')
          hunkgate ci "$ITEM"
```

The gate fails until a human has decided every hunk. That is the
point: the check is not "did the agent's code pass tests" — CI already
does that — it is "did a person actually look at this".

## Pre-commit

```yaml
repos:
  - repo: local
    hooks:
      - id: hunkgate-gate
        name: hunkgate gate
        entry: hunkgate ci
        language: system
        # pass the item id as the argument; see examples/github-action.yml
        # for the full setup
```

## What CI can and cannot do

CI can enforce that the gate is closed. It cannot enforce that the
human *read* the code — an approval with a one-word reason still
passes. If approvals start looking like rubber stamps, the fix is a
team norm (and the audit log, which shows who approved what and why),
not a stricter flag.
