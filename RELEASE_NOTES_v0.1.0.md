# hunkgate v0.1.0 — Release Notes

**The human gate for agent-written code.**

Your agent says "done". hunkgate is the five minutes between that claim
and the merge: capture the diff, see every hunk risk-scored, approve what
you trust, apply only that, and send the rest back to the agent as a
structured prompt. No server, no browser, no model, no network — a
zero-dependency Python CLI that stores everything in `.hunkgate/` inside
your repo.

## What is in v0.1.0

- **Review queue** — `capture` a diff from `git diff`, a file or stdin;
  `list` shows items riskiest first; `show` shows every hunk with its
  findings, evidence and fix hints.
- **24 deterministic risk rules** — secrets and API keys, TLS verification
  off, auth decorators removed, weak hashes, `eval`/`exec`, shell
  execution, unsafe deserialisation, `rm -rf`, `DROP TABLE`, `DELETE`
  without `WHERE`, force-push, migrations, dependency changes, skipped
  tests, empty `except: pass`, debug mode. Every finding names its rule.
- **Risk score 0–100 + bands** — OK (0–19), REVIEW (20–49), BLOCK (50–100).
  The demo fixture scores 95/100: a hardcoded key, `verify=False`, an
  `rmtree` + `DROP TABLE` helper and an `eval()` filter.
- **Decisions with a record** — approve/reject per hunk, per file or
  whole item. Rejecting needs a reason (the agent cannot fix what it
  cannot see); approving a BLOCK hunk needs a reason too. Every decision
  lands in an append-only `audit.jsonl`.
- **Apply only what you approved** — `apply` rebuilds the patch from the
  approved hunks (headers recomputed) and runs `git apply --check` first.
  In the demo, the two approved hunks apply cleanly while the three
  rejected files stay byte-for-byte untouched.
- **Feedback prompt** — `feedback` generates the exact message to send
  back to the agent: approved list, rejected hunks with reasons and
  fixes, open questions.
- **Reports + CI gate** — Markdown / JSON / dark-mode HTML reports, and
  `hunkgate ci` exits 2 until the gate is READY.
- **Config** — `.hunkgate.toml`: reviewer, `auto_approve` (`docs-only`,
  `tests-only`), disable built-in rules, add your own `[[custom_rule]]`.
- **Tests: 90/90 pass** (unittest, no dependencies), clean-venv install
  verified, demo fixture pinned (5 hunks, 8 findings, 95/100, READY).

## Install (source only — no PyPI package yet)

```bash
git clone https://github.com/BidyutRoy2/hunkgate.git
cd hunkgate
python -m pip install -e .
hunkgate demo
```

## How to create the release (maintainer)

1. Upload the files to GitHub as the `hunkgate` repo (see README
   "Upload" section for the description, topics and the multi-commit
   suggestion).
2. Create the tag and release on the repo page:
   - Tag: `v0.1.0` — Title: `hunkgate v0.1.0 — The human gate for agent-written code`
   - Body: paste this file's content above (from "The human gate..." down).
   - Attach `assets/demo.mp4` as a release asset if you want the clip on
     the release page.
3. Upload `assets/social-preview.png` under Settings → General → Social
   preview.
