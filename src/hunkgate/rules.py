"""Deterministic risk rules for agent-written diffs.

Every rule is a plain regex / path check over the *added* lines (and, for
a few rules, the *removed* lines) of a hunk. No model, no network, no
heuristics that need a corpus: a finding either matches or it does not,
and the rule that fired is always named in the output.

Severity ladder (see scoring.py)::

    critical -> 90    high -> 70    medium -> 40    low -> 10

Design rules for adding a rule:

* Match the *smallest* pattern that is actually dangerous. A rule that
  fires on half of all diffs is worse than no rule — it trains reviewers
  to ignore the gate.
* Prefer added lines; a removed line only matters when the removal
  itself is the risk (auth decorator removed, ``verify=False`` added
  is an add; a deleted ``@login_required`` is a removal).
* Every rule has a stable id, a one-line message, and a ``fix`` hint
  that goes into the feedback prompt the agent receives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .diffparse import DiffFile, Hunk

SEVERITY_WEIGHT = {"critical": 90, "high": 70, "medium": 40, "low": 10}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str  # critical | high | medium | low
    message: str
    fix: str
    evidence: str
    line_no: int | None = None  # new-file line number, when known
    direction: str = "add"  # "add" | "del" | "path" | "hunk"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "fix": self.fix,
            "evidence": self.evidence,
            "line_no": self.line_no,
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(**data)


@dataclass
class Rule:
    rule_id: str
    severity: str
    message: str
    fix: str
    patterns: list[re.Pattern] = field(default_factory=list)
    path_patterns: list[re.Pattern] = field(default_factory=list)
    direction: str = "add"  # "add" | "del" | "path" | "hunk"
    hunk_check: object = None  # optional callable(hunk) -> bool


def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern)


# ---------------------------------------------------------------------------
# Rule table. Keep this list in severity order inside each group; the docs
# (docs/rules.md) are generated from it by `hunkgate rules --format md`.
# ---------------------------------------------------------------------------

RULES: list[Rule] = [
    # --- Secrets -----------------------------------------------------------
    Rule("SEC-01", "critical",
         "Possible secret or API key in added code",
         "Move the value to an environment variable or secret store; "
         "rotate it if it was ever committed.",
         patterns=[_re(r"(?i)\b(AKIA[0-9A-Z]{16})\b"),
                   _re(r"(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
                   _re(r"(?i)\b(sk-ant-[A-Za-z0-9_-]{10,}|sk-proj-[A-Za-z0-9_-]{10,})\b"),
                   _re(r"(?i)\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"),
                   _re(r"(?i)\b(api[_-]?key|apikey|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
                   _re(r"(?i)\baws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*['\"][^'\"]{8,}['\"]")]),
    Rule("SEC-02", "critical",
         "Private key material in added code",
         "Never commit key material. Generate keys at deploy time and "
         "store them in a secret manager.",
         patterns=[_re(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")]),
    Rule("SEC-03", "high",
         "Hardcoded password in added code",
         "Read the password from the environment or a secret store; "
         "never ship a literal password.",
         patterns=[_re(r"(?i)\bpassword\s*[:=]\s*['\"][^'\"]{4,}['\"]"),
                   _re(r"(?i)\bpasswd\s*[:=]\s*['\"][^'\"]{4,}['\"]")]),
    Rule("SEC-04", "high",
         "Hardcoded bearer token in added code",
         "Fetch the token at runtime from the environment or secret store.",
         patterns=[_re(r"(?i)\b(bearer\s+[A-Za-z0-9._-]{16,})"),
                   _re(r"(?i)\b(token)\s*[:=]\s*['\"][A-Za-z0-9._-]{20,}['\"]")]),
    # --- Auth / transport --------------------------------------------------
    Rule("AUTH-01", "high",
         "TLS verification disabled",
         "Remove verify=False / unverified contexts. If a test needs it, "
         "scope it to the test and never ship it.",
         patterns=[_re(r"verify\s*=\s*False"),
                   _re(r"ssl\._create_unverified_context\s*\("),
                   _re(r"check_hostname\s*=\s*False"),
                   _re(r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0['\"]?"),
                   _re(r"rejectUnauthorized\s*:\s*false")]),
    Rule("AUTH-02", "high",
         "Authentication decorator removed",
         "Confirm the endpoint is intentionally public. If not, restore "
         "the auth check before merging.",
         direction="del",
         patterns=[_re(r"@\s*(login_required|requires_auth|authenticated|auth_required|authorize)\b"),
                   _re(r"@\s*permission_classes\s*\(")]),
    Rule("AUTH-03", "medium",
         "CORS wide open (any origin allowed)",
         "Restrict allowed origins to the exact domains the app serves.",
         patterns=[_re(r"(?i)Access-Control-Allow-Origin['\"]?\s*[:=]\s*['\"]?\*"),
                   _re(r"CORS.*origins\s*=\s*\[['\"]\*['\"]\]"),
                   _re(r"allow_origins\s*=\s*\[['\"]\*['\"]\]")]),
    # --- Crypto ------------------------------------------------------------
    Rule("CRYPTO-01", "medium",
         "Weak hash (MD5/SHA-1) in added code",
         "Use SHA-256 or better for integrity; use a password-hashing "
         "function (bcrypt/argon2/scrypt) for passwords.",
         patterns=[_re(r"\bmd5\s*\("), _re(r"\bsha1\s*\("),
                   _re(r"hashlib\.(md5|sha1)\s*\(")]),
    Rule("CRYPTO-02", "medium",
         "Non-cryptographic random used where a secret is involved",
         "Use secrets.token_hex / secrets.choice for tokens, passwords "
         "and anything security-sensitive.",
         patterns=[_re(r"random\.(random|choice|randint|randrange)\s*\([^)]*(token|secret|password|key|otp)")]),
    # --- Code execution ----------------------------------------------------
    Rule("EVAL-01", "high",
         "eval()/exec() on (possibly) untrusted input",
         "Replace eval/exec with explicit parsing (ast.literal_eval, a "
         "small parser, or a dispatch table).",
         patterns=[_re(r"\beval\s*\("), _re(r"\bexec\s*\("),
                   _re(r"__import__\s*\("), _re(r"\bcompile\s*\([^)]*,\s*['\"]exec['\"]")]),
    Rule("EVAL-02", "high",
         "Shell execution with a shell / piped install",
         "Avoid shell=True and curl|sh. Use subprocess with an argument "
         "list and no shell.",
         patterns=[_re(r"os\.system\s*\("),
                   _re(r"shell\s*=\s*True"),
                   _re(r"\|\s*(sh|bash)\b"),
                   _re(r"curl\b[^|]*\|\s*sh\b")]),
    Rule("EVAL-03", "high",
         "Unsafe deserialisation (pickle / yaml.load without a loader)",
         "Use json, or pickle only on data you produced yourself; pass "
         "an explicit SafeLoader to yaml.load.",
         patterns=[_re(r"pickle\.(loads|load)\s*\("),
                   _re(r"yaml\.load\s*\([^)]*\)\s*$"),
                   _re(r"marshal\.(loads|load)\s*\("),
                   _re(r"yaml\.unsafe_load\s*\(")]),
    Rule("EVAL-04", "medium",
         "SQL built by string interpolation",
         "Use parameterised queries (placeholders) instead of f-strings "
         "or % formatting in SQL.",
         patterns=[_re(r"execute\s*\(\s*f['\"]"),
                   _re(r"execute\s*\(.*%\s*\(?"),
                   _re(r"executemany\s*\(\s*f['\"]")]),
    # --- Destructive operations -------------------------------------------
    Rule("DESTRUCT-01", "critical",
         "Recursive delete (rm -rf) in added code",
         "Delete with an explicit, narrow path and a guard (refuse to "
         "delete outside the workspace).",
         patterns=[_re(r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b"),
                   _re(r"shutil\.rmtree\s*\(")]),
    Rule("DESTRUCT-02", "critical",
         "DROP / TRUNCATE in added code",
         "Destructive schema statements need a migration with a backup "
         "and a human-approved rollout plan.",
         patterns=[_re(r"(?i)\bDROP\s+(TABLE|DATABASE|SCHEMA)\b"),
                   _re(r"(?i)\bTRUNCATE\s+TABLE\b")]),
    Rule("DESTRUCT-03", "high",
         "DELETE without WHERE in this hunk",
         "Add a WHERE clause (or an explicit --all flag) so a delete "
         "cannot wipe a whole table by accident.",
         direction="hunk",
         hunk_check=lambda h: (
             any(re.search(r"(?i)\bDELETE\s+FROM\b", ln.text)
                 for ln in h.added)
             and not any("WHERE" in ln.text.upper()
                         for ln in h.added + h.removed))),
    Rule("DESTRUCT-04", "medium",
         "Force-push in added code or docs",
         "Use --force-with-lease, and never force-push shared branches.",
         patterns=[_re(r"git\s+push\s+.*--force(?!-with-lease)"),
                   _re(r"git\s+push\s+-[a-z]*f\b")]),
    # --- Migrations / dependencies ----------------------------------------
    Rule("MIGR-01", "high",
         "Schema / migration change",
         "Ship the migration with a rollback and a backfill plan; review "
         "it against a copy of production data first.",
         direction="path",
         path_patterns=[_re(r"(?i)(^|/)migrations?/"),
                        _re(r"(?i)alembic/versions/"),
                        _re(r"(?i)\.sql$")]),
    Rule("DEPS-01", "medium",
         "Dependency or lockfile change",
         "Pin the new dependency, check its source and licence, and make "
         "sure CI still passes.",
         direction="path",
         path_patterns=[_re(r"(^|/)(requirements[^/]*\.txt|Pipfile|pyproject\.toml|setup\.py|setup\.cfg)$"),
                        _re(r"(^|/)(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$"),
                        _re(r"(^|/)(Cargo\.toml|Cargo\.lock|go\.mod|go\.sum|Gemfile|Gemfile\.lock|composer\.json|composer\.lock)$")]),
    # --- Network -----------------------------------------------------------
    Rule("NET-01", "low",
         "New outbound network call",
         "Confirm the endpoint, timeout and retry policy; log failures "
         "without leaking credentials.",
         patterns=[_re(r"requests\.(get|post|put|delete|patch)\s*\("),
                   _re(r"urllib\.request\.urlopen\s*\("),
                   _re(r"httpx\.(get|post|request)\s*\("),
                   _re(r"\bfetch\s*\("), _re(r"axios\.(get|post)\s*\(")]),
    # --- Tests -------------------------------------------------------------
    Rule("TEST-01", "medium",
         "Test skipped or marked xfail",
         "A skipped test is a promise to look later. Say why it is "
         "skipped and when it comes back.",
         patterns=[_re(r"@pytest\.mark\.skip"),
                   _re(r"@pytest\.mark\.xfail"),
                   _re(r"@unittest\.skip"),
                   _re(r"\.skip\s*\(\s*['\"]")]),
    Rule("TEST-02", "medium",
         "Empty exception handler (except: pass)",
         "Log the exception or handle it explicitly — silent swallowing "
         "hides the failures reviewers need to see.",
         direction="hunk",
         hunk_check=lambda h: _has_empty_except(h)),
    # --- Misc --------------------------------------------------------------
    Rule("SEC-05", "medium",
         "Debug mode enabled",
         "Debug mode leaks stack traces and internals. Keep it off "
         "outside local development.",
         patterns=[_re(r"(?i)\bDEBUG\s*=\s*True\b"),
                   _re(r"app\.run\s*\([^)]*debug\s*=\s*True"),
                   _re(r"debug\s*=\s*True")]),
    Rule("DOC-01", "low",
         "Documentation-only change",
         "Safe to approve on its own — but check the claims still match "
         "the code.",
         direction="path",
         path_patterns=[_re(r"\.(md|rst|txt)$"),
                        _re(r"(^|/)(docs|doc)/")]),
]


def _has_empty_except(hunk: Hunk) -> bool:
    """True when an added ``pass`` directly follows an added ``except``."""
    prev_added = ""
    for line in hunk.lines:
        if line.kind != "add":
            continue
        if line.text.strip() == "pass" and prev_added.strip().startswith("except"):
            return True
        prev_added = line.text
    return False


def _is_test_path(path: str) -> bool:
    return bool(re.search(r"(^|/)(test_|_test\.|tests?/|__tests__/|\.test\.)", path))


def _is_docs_path(path: str) -> bool:
    return bool(re.search(r"\.(md|rst|txt)$", path)
                or re.search(r"(^|/)(docs|doc)/", path))


def check_hunk(diff_file: DiffFile, hunk: Hunk,
               extra: list[Rule] | None = None,
               disabled: set[str] | frozenset | None = None) -> list[Finding]:
    """Run every rule over one hunk; return findings in rule order.

    ``extra`` adds config-defined custom rules; ``disabled`` skips
    built-in rules by id.
    """
    findings: list[Finding] = []
    disabled = disabled or set()
    for rule in list(RULES) + list(extra or []):
        if rule.rule_id in disabled:
            continue
        if rule.direction == "path":
            if any(p.search(diff_file.path) for p in rule.path_patterns):
                findings.append(Finding(
                    rule_id=rule.rule_id, severity=rule.severity,
                    message=rule.message, fix=rule.fix,
                    evidence=diff_file.path, direction="path"))
            continue
        if rule.direction == "hunk":
            if rule.hunk_check is not None and rule.hunk_check(hunk):
                evidence = next(
                    (ln.text for ln in hunk.added
                     if ln.text.strip()), "(hunk)")
                findings.append(Finding(
                    rule_id=rule.rule_id, severity=rule.severity,
                    message=rule.message, fix=rule.fix,
                    evidence=evidence.strip()[:120], direction="hunk"))
            continue
        lines = hunk.added if rule.direction == "add" else hunk.removed
        for line in lines:
            for pattern in rule.patterns:
                if pattern.search(line.text):
                    findings.append(Finding(
                        rule_id=rule.rule_id, severity=rule.severity,
                        message=rule.message, fix=rule.fix,
                        evidence=line.text.strip()[:120],
                        line_no=line.new_no if rule.direction == "add"
                        else line.old_no,
                        direction=rule.direction))
                    break  # one finding per rule per line
    return findings


def check_item(diff) -> dict:
    """Item-level findings that no single hunk can see.

    Currently: TEST-03 — code changed but no test file changed.
    Returns a dict of item-level finding dicts (JSON-ready).
    """
    findings: list[Finding] = []
    code_files = [f for f in diff.files
                  if not f.binary and not _is_docs_path(f.path)
                  and f.status != "deleted"]
    test_files = [f for f in diff.files if _is_test_path(f.path)]
    if code_files and not test_files:
        findings.append(Finding(
            rule_id="TEST-03", severity="medium",
            message="Code changed but no test file changed",
            fix="Add or update a test that covers the new behaviour, or "
                "record why this change needs none.",
            evidence=", ".join(f.path for f in code_files)[:120],
            direction="hunk"))
    return {"findings": [f.to_dict() for f in findings]}


def rule_table() -> list[dict]:
    """The rule table as data (for docs generation and `rules` output)."""
    return [{"rule_id": r.rule_id, "severity": r.severity,
             "message": r.message, "fix": r.fix,
             "direction": r.direction} for r in RULES]
