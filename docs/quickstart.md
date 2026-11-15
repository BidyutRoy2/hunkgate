# Quickstart

## Install

No PyPI package is published yet — install from source:

```bash
git clone https://github.com/BidyutRoy2/hunkgate.git
cd hunkgate
python -m pip install -e .
```

Python 3.9+; zero dependencies. Verify with `hunkgate demo` — it runs
the bundled fixture end to end and should end with `gate READY`.

## Your first review (5 minutes)

```bash
cd your-project
hunkgate init                              # create .hunkgate/

# The agent just finished. Capture what it did:
git diff > /tmp/agent.diff
hunkgate capture /tmp/agent.diff --agent claude-code --title "Add login"

hunkgate list                              # the queue, riskiest first
hunkgate show HG-20261115-123045-a1b2c3    # hunks + findings + scores
```

Decide on each hunk. Rejecting needs a reason — the agent cannot fix
what it cannot see. Approving a BLOCK hunk needs a reason too.

```bash
hunkgate reject HG-... F1.1 --reason "Hardcoded key — use an env var"
hunkgate reject HG-... F2.1 --reason "DROP TABLE needs a migration plan"
hunkgate approve HG-... F4.1 --reason "Skip is temporary, tracked in #12"
```

Then apply only what you approved, and get the prompt to send back:

```bash
hunkgate apply HG-...        # approved hunks only; rejected files untouched
hunkgate feedback HG-...     # copy-paste this back to the agent
hunkgate report HG-... --format md   # the record
```

## The four decisions

| Command | When |
|---|---|
| `approve <item> <hunk>` | You read the hunk and it is fine. BLOCK hunks need `--reason`. |
| `reject <item> <hunk> --reason ...` | It must change. The reason is what the agent gets. |
| `comment <item> --text ...` | A note or question that is not a verdict. |
| (nothing) | The hunk stays `pending` — the gate stays closed. |

Targets are hunk ids (`F1.2`), file ids (`F1` = every hunk in that
file), or `all`. New and deleted files are always decided as a whole:
a partial new file is not a thing.

## Auto-approve the boring parts

Docs-only and tests-only hunks can auto-approve at capture time:

```bash
hunkgate capture changes.diff --auto-approve docs-only tests-only
```

Or set it in `.hunkgate.toml` (see `examples/hunkgate.toml`). An
auto-approval is recorded as a decision with the policy name, so the
audit log still shows who — or what — approved it.
