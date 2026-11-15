# Risk rules

Every rule is a deterministic pattern over the added lines (a few over
removed lines, or over the file path). A finding always names its rule,
its severity, the evidence that matched, and a fix hint. Run
`hunkgate rules` for the same table from the CLI, or
`hunkgate rules --format md` to regenerate this page.

| Rule | Severity | What it catches |
|---|---|---|
| SEC-01 | critical | Possible secret or API key in added code (AWS keys, GitHub tokens, Anthropic/OpenAI keys, Slack tokens, `api_key = "..."`) |
| SEC-02 | critical | Private key material (`-----BEGIN ... PRIVATE KEY-----`) |
| SEC-03 | high | Hardcoded password (`password = "..."`) |
| SEC-04 | high | Hardcoded bearer token |
| SEC-05 | medium | Debug mode enabled (`DEBUG = True`, `debug=True`) |
| AUTH-01 | high | TLS verification disabled (`verify=False`, unverified contexts, `rejectUnauthorized: false`) |
| AUTH-02 | high | Authentication decorator removed (`@login_required`, `@requires_auth`, …) |
| AUTH-03 | medium | CORS wide open (any origin allowed) |
| CRYPTO-01 | medium | Weak hash (MD5/SHA-1) |
| CRYPTO-02 | medium | Non-cryptographic random used for a token/secret/password |
| EVAL-01 | high | `eval()` / `exec()` / `__import__()` |
| EVAL-02 | high | Shell execution (`os.system`, `shell=True`, `curl … | sh`) |
| EVAL-03 | high | Unsafe deserialisation (`pickle.loads`, `yaml.load` without a loader, `marshal`) |
| EVAL-04 | medium | SQL built by string interpolation (`execute(f"…")`) |
| DESTRUCT-01 | critical | Recursive delete (`rm -rf`, `shutil.rmtree`) |
| DESTRUCT-02 | critical | `DROP TABLE` / `DROP DATABASE` / `TRUNCATE` |
| DESTRUCT-03 | high | `DELETE FROM` without `WHERE` in the hunk |
| DESTRUCT-04 | medium | Force-push (`git push --force`, not `--force-with-lease`) |
| MIGR-01 | high | Schema / migration change (migrations dir, Alembic versions, `.sql` files) |
| DEPS-01 | medium | Dependency or lockfile change (`requirements.txt`, `package.json`, `Cargo.toml`, …) |
| NET-01 | low | New outbound network call (`requests.get`, `fetch(`, …) |
| TEST-01 | medium | Test skipped or marked xfail |
| TEST-02 | medium | Empty exception handler (`except: pass`) |
| TEST-03 | medium | Code changed but no test file changed (item-level, not per hunk) |
| DOC-01 | low | Documentation-only change (used by the `docs-only` auto-approve policy) |

## Severity and scores

| Severity | Weight |
|---|---|
| critical | 90 |
| high | 70 |
| medium | 40 |
| low | 10 |

A hunk's score is the highest finding weight plus 5 per additional
finding, capped at 100. See [scoring.md](scoring.md).

## Custom rules

Add your own in `.hunkgate.toml`:

```toml
[[custom_rule]]
id = "ACME-01"
severity = "high"
pattern = "TODO\\(acme\\)"
message = "ACME TODO left in code"
fix = "Resolve the TODO or file a ticket and link it."
direction = "add"   # add | del | path
```

Disable a built-in rule the same way:

```toml
[rules.SEC-05]
enabled = false
```

A custom rule is one regex over one line (or path). If the pattern
needs more than that — multi-line context, cross-file reasoning — it
does not belong in the rule engine; write the check as a review comment
instead.
