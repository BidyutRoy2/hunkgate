# Contributing to hunkgate

Thanks for helping make the human gate better. This guide is short on
purpose: the project is a zero-dependency Python CLI, and the bar for a
change is that it stays that way.

## Setup

```bash
git clone https://github.com/BidyutRoy2/hunkgate.git
cd hunkgate
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

No PyPI package is published yet, so install from source. There are no
runtime dependencies and no dev dependencies either — the test suite is
plain `unittest`.

## Running the tests

```bash
# From a bare clone (the -t . matters: it imports tests as a package so
# the src-layout bootstrap in tests/__init__.py runs):
python -m unittest discover -s tests -t .

# Or with pytest, if you have it:
python -m pytest
```

## Rules for changes

1. **Zero dependencies, forever.** Standard library only. If a feature
   seems to need a library, it needs a smaller design instead.
2. **Deterministic or it does not ship.** Same diff in, same scores,
   same patch out. No randomness, no wall-clock in scoring, no network.
3. **A rule that fires on half of all diffs is a bug.** New risk rules
   must match the smallest pattern that is actually dangerous, and must
   come with a positive test *and* a negative test (see `tests/test_rules.py`).
4. **The demo fixture is pinned.** `hunkgate demo` must always print
   risk 95/100, 5 hunks, 8 findings, gate READY. If your change moves
   those numbers, update the fixture or the docs — and say so in the PR.
5. **Honest limits.** If the tool cannot know something, say so in the
   output and in `docs/limits.md`. Never paper over uncertainty with a
   confident-looking number.
6. **Keep the audit log append-only.** Decisions are history. Never
   rewrite `audit.jsonl` in code, and never add a command that edits it.

## Adding a risk rule

1. Add the `Rule` to `src/hunkgate/rules.py` (severity order inside its
   group) with a `fix` hint the agent can act on.
2. Add a positive and a negative test in `tests/test_rules.py`.
3. Add a row to the rule table in `docs/rules.md` (or regenerate it with
   `hunkgate rules --format md`).
4. If the rule changes the demo fixture's score, update `docs/scoring.md`
   and the pinned numbers in `src/hunkgate/demo.py`.

## Style

- Python 3.9 compatible (no `match`, no `tomllib` at runtime — the config
  parser has a hand-rolled fallback).
- `black`-ish formatting, 4-space indent, type hints on public functions.
- Keep functions small and pure where possible: parsing, scoring and
  patch-building are all testable without a filesystem.

## Reporting bugs

Use the bug template (`.github/ISSUE_TEMPLATE/bug_report.md`) and include
the smallest diff that reproduces the problem. Never paste real secrets —
redact them first; the scanner is designed to catch them, and the issue
tracker is public.
