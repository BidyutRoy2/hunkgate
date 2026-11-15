# FAQ

## Does hunkgate replace code review?

No. It orders the queue and catches known-bad patterns so your review
time goes to the dangerous hunks first. Reading the code is still your
job — a hunk that scores 0 can still be wrong.

## Does it run the agent's code?

No. The only commands it runs are `git diff` (read-only) and
`git apply` (on a patch you approved). It never executes agent code,
and it has no network code at all.

## What if the agent re-submits the same bad code?

Reject it again with the same reason. The audit log shows the history,
and the feedback prompt tells the agent to disagree in words rather
than silently re-add the code. If an agent keeps re-submitting rejected
work, that is a workflow problem (or a prompt problem), not a tool
problem.

## Why can I not approve a BLOCK hunk without a reason?

Because "I looked at the secret and it is fine" is a claim that belongs
on the record. If it really is fine — a documented example key, a test
fixture — saying so takes ten seconds and protects the next person who
reads the audit log.

## Can the agent approve its own work?

Only if you hand it the terminal. Decisions are CLI commands run by a
human; there is no API, no web page and no agent integration. Keep it
that way: never pipe an agent's output into `hunkgate approve`.

## What happens if a kept hunk depends on a dropped one?

`git apply --check` fails and `apply` refuses to write anything. Re-
review: either approve the dependency too (with a reason), or reject
the dependent hunk as well and tell the agent to split them.

## Does it work without git?

`capture` from `--file` or `--stdin` works anywhere. `apply` needs git
(it shells out to `git apply`). `capture` from `git diff` obviously
needs a repo.

## Can I use it for human-written diffs?

Yes. Nothing in the rules cares who wrote the code. The queue is just
as useful for a colleague's PR — though for PRs, `capture --base main`
is the usual entry point.

## Is my review data sent anywhere?

Nowhere. Everything lives in `.hunkgate/` on your disk. There is no
account, no telemetry, no network call in the codebase.
