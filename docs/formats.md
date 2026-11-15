# Formats — store, reports, feedback

## The store (`.hunkgate/`)

```
.hunkgate/
  items/
    HG-20261115-123045-a1b2c3.json
  audit.jsonl
```

An item file is plain JSON: metadata (`id`, `created`, `source`,
`agent`, `title`), the parsed diff (files, hunks, lines, findings,
scores) and one decision per hunk (`pending` / `approved` /
`rejected` / `auto-approved`, with `decision_by`, `decision_at` and
`decision_reason`). You can read it with any JSON tool; you should not
edit it by hand — use the CLI so the audit log stays in sync.

`audit.jsonl` is append-only: one JSON object per line, one per event
(`approved`, `rejected`, `comment`, `auto-approve`), with a timestamp.
It is never rewritten. If you need the history of an item, that file is
the record.

The store is git-ignored by default (see `.gitignore`). If you commit
it, remember a captured diff can contain a real secret — rotate the
secret first, then delete the item file.

## Reports

`hunkgate report <item> --format md|json|html` renders the stored item.
Reports never re-score the diff, so the numbers always match `show`.

- **Markdown** — the record for a PR description or a review thread.
- **JSON** — machine-readable: risk, verdict, hunks, findings, audit.
- **HTML** — a dark-mode-aware page (inline CSS, no network) for
  sharing with someone who does not have the CLI.

## The feedback prompt

`hunkgate feedback <item>` prints a Markdown prompt for the agent:

1. **Approved — keep as-is** (hunk ids, files, scores).
2. **Rejected — fix before re-submitting** (per hunk: the reason, each
   finding with its fix hint and evidence).
3. **Still undecided** (if any).
4. **Reviewer notes** (comments, if any).
5. **How to re-submit** (fix the rejected hunks, submit a *new* diff,
   disagree in words — never silently re-add the same code).

A rejected hunk without a reason cannot exist: the store refuses the
decision. So the prompt never says "fix this" without saying what
"this" is.
