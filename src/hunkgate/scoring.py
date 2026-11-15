"""Scoring: hunk risk 0-100, bands, and the gate verdict.

The score is deliberately boring and explainable:

* base = weight of the single most severe finding
  (critical 90, high 70, medium 40, low 10, none 0)
* +5 for every additional finding, capped at 100

Bands::

    0-19   OK      — safe to approve on its own
    20-49  REVIEW  — a human should look, but nothing blocks the merge
    50-100 BLOCK   — do not merge until a human has decided on this hunk

The gate verdict for a whole item:

* READY   — every hunk decided (approved / rejected / auto-approved)
* REVIEW  — no BLOCK hunk undecided, but some REVIEW/OK hunks are
* BLOCKED — at least one BLOCK hunk is still undecided
"""

from __future__ import annotations

from .rules import SEVERITY_WEIGHT, Finding

BANDS = ((50, "BLOCK"), (20, "REVIEW"), (0, "OK"))


def hunk_score(findings: list[Finding]) -> int:
    """Risk score 0-100 for one hunk from its findings."""
    if not findings:
        return 0
    base = max(SEVERITY_WEIGHT[f.severity] for f in findings)
    return min(100, base + 5 * (len(findings) - 1))


def band(score: int) -> str:
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "OK"


def grade_band(score: int) -> str:
    return band(score)


def is_docs_only(findings: list[Finding], path: str) -> bool:
    """True when the hunk is only documentation (path + findings agree)."""
    from .rules import _is_docs_path

    if not _is_docs_path(path):
        return False
    return all(f.rule_id == "DOC-01" for f in findings)


def is_tests_only(findings: list[Finding], path: str) -> bool:
    """True when the hunk only touches test files with no real findings."""
    from .rules import _is_test_path

    if not _is_test_path(path):
        return False
    return all(f.severity in ("low",) for f in findings)


def coverage(decided: int, total: int) -> int:
    """Review coverage 0-100: share of hunks with a decision."""
    if total == 0:
        return 100
    return round(100 * decided / total)


def verdict(hunks: list[dict]) -> dict:
    """Gate verdict for an item from its hunk dicts.

    Each hunk dict needs ``score`` and ``decision`` (``pending``,
    ``approved``, ``rejected`` or ``auto-approved``).
    """
    undecided_block = [h for h in hunks
                       if h["decision"] == "pending" and band(h["score"]) == "BLOCK"]
    undecided = [h for h in hunks if h["decision"] == "pending"]
    decided = len(hunks) - len(undecided)
    if undecided_block:
        state = "BLOCKED"
    elif undecided:
        state = "REVIEW"
    else:
        state = "READY"
    return {
        "state": state,
        "coverage": coverage(decided, len(hunks)),
        "decided": decided,
        "total": len(hunks),
        "undecided_block": len(undecided_block),
        "undecided": len(undecided),
        "approved": sum(1 for h in hunks if h["decision"] in ("approved", "auto-approved")),
        "rejected": sum(1 for h in hunks if h["decision"] == "rejected"),
    }
