# Changelog

All notable changes to hunkgate are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-15

### Added

- `init` / `capture` / `list` / `show` — review queue backed by a local
  `.hunkgate/` store (one JSON file per item, append-only `audit.jsonl`).
- Deterministic risk rules (24 built-in): secrets, auth bypass, weak
  crypto, eval/shell execution, unsafe deserialisation, destructive
  operations, migrations, dependency changes, network calls, skipped
  tests, empty handlers, debug mode, docs-only. Each finding names its
  rule, its evidence and a fix hint.
- Risk scoring 0–100 with bands OK / REVIEW / BLOCK, and a gate verdict
  (READY / REVIEW / BLOCKED) with review coverage.
- `approve` / `reject` / `comment` — per-hunk, per-file or whole-item
  decisions. Rejecting needs a reason; approving a BLOCK hunk needs a
  reason. New/deleted files are decided as a whole.
- `apply` — builds an approved-only patch (headers recomputed) and runs
  `git apply --check` before `git apply`; refuses to apply a patch that
  does not apply cleanly.
- `feedback` — a structured, copy-paste prompt back to the agent:
  approved hunks, rejected hunks with reasons and fixes, open questions.
- `report` — Markdown / JSON / dark-mode-aware HTML reports derived from
  the stored item (never re-scored, so numbers always match `show`).
- `ci` — exit 2 unless the gate is READY (`--allow-review` also passes
  when only REVIEW/OK hunks are undecided).
- `doctor` — checks the store, git and config.
- `rules` — list the built-in rules as text, JSON or Markdown.
- `.hunkgate.toml` config: reviewer name, `auto_approve` policies
  (`docs-only`, `tests-only`), disabling built-in rules, custom rules
  (`[[custom_rule]]`).
- `demo` — the bundled fixture: 5 files, 5 hunks, 8 findings, risk
  95/100, gate READY after 3 rejections and 2 approvals.
- Full docs (`docs/`), examples (`examples/demo.diff`,
  `examples/hunkgate.toml`, `examples/demo.sh`), CI on Python 3.9–3.13
  (Ubuntu/macOS/Windows), issue/PR templates, Dependabot.
