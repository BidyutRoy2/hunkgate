# Review report — HG-20261115-070425-25c7be

**Add login + cleanup (agent run #42)** · created 2026-11-15T07:04:25+00:00 · source `demo.diff`

Risk: **95/100 (BLOCK)** · Files: 5 · Hunks: 5 · Findings: 8

Gate: **READY** — coverage 100% (5/5 hunks decided, 2 approved, 3 rejected, 0 undecided, 0 blocking)

## Hunks

| Hunk | File | Risk | Decision | Findings |
|---|---|---|---|---|
| F1.1 | `src/auth.py` | 95 (BLOCK) | rejected | SEC-01, AUTH-01 |
| F2.1 | `src/db.py` | 95 (BLOCK) | rejected | DESTRUCT-01, DESTRUCT-02 |
| F3.1 | `src/api.py` | 75 (BLOCK) | rejected | EVAL-01, NET-01 |
| F4.1 | `tests/test_api.py` | 40 (REVIEW) | approved | TEST-01 |
| F5.1 | `README.md` | 10 (OK) | auto-approved | DOC-01 |

### F1.1 · `src/auth.py` — 95/100 BLOCK

- **[SEC-01]** Possible secret or API key in added code
  - Evidence: `API_KEY = "sk-live-9f2c7d1a4b6e8f0a"`
  - Fix: Move the value to an environment variable or secret store; rotate it if it was ever committed.
- **[AUTH-01]** TLS verification disabled
  - Evidence: `session.verify = False`
  - Fix: Remove verify=False / unverified contexts. If a test needs it, scope it to the test and never ship it.
- Decision reason: Hardcoded API key + verify=False. Move the key to an env var and drop verify=False.

### F2.1 · `src/db.py` — 95/100 BLOCK

- **[DESTRUCT-01]** Recursive delete (rm -rf) in added code
  - Evidence: `shutil.rmtree("/var/lib/tracker/data")`
  - Fix: Delete with an explicit, narrow path and a guard (refuse to delete outside the workspace).
- **[DESTRUCT-02]** DROP / TRUNCATE in added code
  - Evidence: `conn.execute("DROP TABLE sessions")`
  - Fix: Destructive schema statements need a migration with a backup and a human-approved rollout plan.
- Decision reason: DROP TABLE + rmtree in one helper. Split into a migration with a backup plan.

### F3.1 · `src/api.py` — 75/100 BLOCK

- **[EVAL-01]** eval()/exec() on (possibly) untrusted input
  - Evidence: `return [i for i in items if eval(user_filter)]`
  - Fix: Replace eval/exec with explicit parsing (ast.literal_eval, a small parser, or a dispatch table).
- **[NET-01]** New outbound network call
  - Evidence: `return requests.get("https://status.example.com/health", timeout=5)`
  - Fix: Confirm the endpoint, timeout and retry policy; log failures without leaking credentials.
- Decision reason: eval() on user input. Use a parser, not eval.

### F4.1 · `tests/test_api.py` — 40/100 REVIEW

- **[TEST-01]** Test skipped or marked xfail
  - Evidence: `@pytest.mark.skip(reason="flaky on CI, see #12")`
  - Fix: A skipped test is a promise to look later. Say why it is skipped and when it comes back.
- Decision reason: Skip is temporary and tracked in #12.

### F5.1 · `README.md` — 10/100 OK

- **[DOC-01]** Documentation-only change
  - Evidence: `README.md`
  - Fix: Safe to approve on its own — but check the claims still match the code.
- Decision reason: policy: docs-only

## Audit trail

-  · auto-approve · HG-20261115-070425-25c7be ·  
- 2026-11-15T07:04:25+00:00 · rejected · F1.1 · ada — Hardcoded API key + verify=False. Move the key to an env var and drop verify=False.
- 2026-11-15T07:04:25+00:00 · rejected · F2.1 · ada — DROP TABLE + rmtree in one helper. Split into a migration with a backup plan.
- 2026-11-15T07:04:25+00:00 · rejected · F3.1 · ada — eval() on user input. Use a parser, not eval.
- 2026-11-15T07:04:25+00:00 · approved · F4.1 · ada — Skip is temporary and tracked in #12.
