# The review workflow

## The loop

```
agent works            hunkgate capture       you decide
  (any agent,            (diff in,             (approve / reject
   any harness)           risk-scored           per hunk)
        │                     │                     │
        │                     ▼                     ▼
        │              review queue            apply approved
        │              (list / show)           only
        │                     │                     │
        └────── feedback prompt ◄───────────────────┘
               (rejected hunks + reasons + fixes)
```

1. **Capture.** The agent's work arrives as a diff — `git diff`, a
   patch file, or stdin. hunkgate parses it, splits it into hunks and
   scores each one. Nothing is executed and nothing leaves the machine.
2. **Triage.** `list` orders items by risk; `show` shows the findings
   with their evidence. Start at the BLOCK hunks — they are the ones
   that can hurt you.
3. **Decide.** Approve, reject (with a reason) or comment. A hunk with
   no decision keeps the gate closed. That is the whole point: silence
   is not approval.
4. **Apply.** `apply` rebuilds the patch from the approved hunks only
   and runs `git apply --check` first. If a kept hunk depends on a
   dropped neighbour, the check fails and nothing is applied — a
   half-applied tree would be worse than a refusal.
5. **Feed back.** `feedback` generates the exact message for the agent:
   what was approved, what was rejected and why, and what to fix. The
   agent re-submits a *new* diff; the old one stays on the record.

## Where it fits

- **Solo, after every agent session.** The five-minute gate between
  "done" and the merge. This is the primary use case.
- **In CI, as a merge gate.** `hunkgate ci <item>` exits 2 until the
  gate is READY. See [ci.md](ci.md).
- **In a team.** The reviewer is whoever runs the commands; decisions
  are recorded by name in `audit.jsonl`. The person who asked the
  agent for the change should not be its only reviewer — they see what
  they expected to see. Hand the item to someone else when the stakes
  are high.

## What it is not

- **Not a code review replacement.** It orders the queue and catches
  known-bad patterns. Reading the code is still your job.
- **Not a sandbox.** It does not run agent code and does not stop an
  agent mid-session. If you need execution guardrails, pair it with a
  sandbox (see [prior-art.md](prior-art.md)).
- **Not a merge tool.** It applies approved hunks to your working tree;
  the commit and the merge are yours.
