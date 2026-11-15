# Limits — what hunkgate cannot know

Read this before trusting a green gate.

## It cannot see what the diff does not contain

- **Runtime behaviour.** A hunk can be pattern-clean and still delete
  your data at runtime (a logic bug, a wrong table name in a variable,
  a misconfigured cron). The rules see text, not behaviour.
- **The rest of the repo.** A hunk that adds `import helper` is fine
  on its own; whether `helper` is safe is a different question. The
  rules do not follow imports.
- **Intent.** `rmtree("/tmp/work")` and `rmtree(user_input)` look
  similar to a regex. The first is routine cleanup; the second is a
  vulnerability. The rule fires on both, and the human decides which
  one it is. That is the design, not a bug — but it means the score is
  a triage aid, not a verdict.

## It cannot know your context

- **"Test-only" is a guess.** A test file can contain production
  credentials (a fixture with a real key). The `tests-only`
  auto-approve policy trusts the path, not the content — the secret
  rules still fire on test files, and they should.
- **Custom rules are regexes.** One pattern over one line. Anything
  that needs multi-line context or cross-file reasoning does not belong
  in the engine.
- **Scores are not comparable across items.** A 40 in a docs fix and a
  40 in a 500-line refactor mean different things.

## It cannot enforce honesty

- **Approvals are commands.** A human can approve everything with
  `--reason ok`. The audit log records it, but the tool cannot make
  the human read the code.
- **The store is local and editable.** `.hunkgate/` is JSON on disk.
  Anyone with write access can edit an item or the audit log. If the
  audit log is evidence for compliance, keep the repo access tight and
  treat the log as a record, not a proof.
- **Secrets in a captured diff are stored.** Capturing a diff that
  contains a real key writes that key into `.hunkgate/items/`. Rotate
  the key, then delete the item. hunkgate never sends the diff
  anywhere, but a local copy is still a copy.

## It cannot apply what git cannot apply

`apply` refuses when the approved patch does not apply cleanly — for
example when a kept hunk's context changed because a dropped neighbour
was removed. That is deliberate. Do not work around it by hand-editing
the patch; re-review instead.
