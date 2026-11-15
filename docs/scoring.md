# Scoring

## Hunk risk 0–100

```
score = min(100, max_weight + 5 × (findings − 1))
```

where `max_weight` is the weight of the most severe finding:

| Severity | Weight |
|---|---|
| critical | 90 |
| high | 70 |
| medium | 40 |
| low | 10 |
| none | 0 |

Examples:

| Findings | Score | Band |
|---|---|---|
| none | 0 | OK |
| one low (docs-only) | 10 | OK |
| one medium (skipped test) | 40 | REVIEW |
| one high (`eval()`) | 70 | BLOCK |
| one critical + one high (key + `verify=False`) | 95 | BLOCK |
| five critical | 100 | BLOCK |

## Bands

| Band | Range | Meaning |
|---|---|---|
| OK | 0–19 | Safe to approve on its own. |
| REVIEW | 20–49 | A human should look, but nothing here blocks the merge. |
| BLOCK | 50–100 | Do not merge until a human has decided on this hunk. |

## Item risk

The item's risk is the highest hunk score. One bad hunk makes the
whole item BLOCK — averaging would hide it.

## Gate verdict

| Verdict | Meaning |
|---|---|
| READY | Every hunk decided (approved, rejected or auto-approved). |
| REVIEW | No BLOCK hunk undecided, but some REVIEW/OK hunks are. |
| BLOCKED | At least one BLOCK hunk is still undecided. |

Review coverage is decided hunks ÷ total hunks, as a percentage.
`hunkgate ci` exits 0 only on READY (or on REVIEW with
`--allow-review`).

## What the score is not

- **Not a quality score.** A hunk can score 0 and still be wrong. The
  score measures *known risky patterns*, not correctness.
- **Not comparable across diffs.** A 40 in a two-line docs fix and a 40
  in a 500-line refactor mean different things. Compare hunks inside
  one item, not items against each other.
- **Not a substitute for reading.** The score orders the queue so you
  read the dangerous hunks first. It never reads them for you.
