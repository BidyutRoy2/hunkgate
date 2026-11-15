# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes — security fixes only, no new features on the 0.1 line |

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Email the maintainer
(see `SUPPORT.md`) with:

- what the problem is and where it lives (file + line if you can),
- a minimal reproduction (a diff that triggers it is ideal),
- what you think the impact is.

You will get an acknowledgement within 7 days, and a fix or a plan within
30 days. If the issue is confirmed, the fix ships in a patch release and
the advisory is published in the release notes.

## What hunkgate does — and does not — promise

hunkgate is a *decision aid*, not a security scanner and not a sandbox:

- **It does not execute agent code.** The only command it runs is
  `git apply` (on a patch you approved) and `git diff` (read-only).
  Never point `hunkgate apply` at a repo you would not edit by hand.
- **Its rules are patterns, not proofs.** A hunk with no findings is
  "no known pattern matched", not "safe". A hunk with findings is
  "look here", not "guilty". The human decision is the security control;
  the tool only orders the queue.
- **The audit log is local.** `.hunkgate/audit.jsonl` lives in your repo
  (and is git-ignored by default). If you commit it, anyone with repo
  access can read your review history — including rejected secrets'
  file paths. Never commit a review store that contains real secrets;
  rotate the secret first.
- **Secrets in diffs are still secrets.** If an agent writes a real key
  into a diff, capturing that diff stores the key in `.hunkgate/items/`.
  Rotate the key, then delete the item file. hunkgate never sends the
  diff anywhere — it has no network code at all — but a local copy is
  still a copy.
