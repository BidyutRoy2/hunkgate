# Prior art — how hunkgate differs

The human-in-the-loop wave of late 2026 produced several good tools.
hunkgate is deliberately the smallest one: a CLI decision workflow, not
a workspace, not a hook, not a filter.

| Tool | What it is | How hunkgate differs |
|---|---|---|
| [plannotator](https://plannotator.ai) | Browser workspace (TypeScript) for reviewing agent plans and code, annotating, and sending feedback back. Trending #1 on GitHub, Nov 2026. | hunkgate is the same *job* (human decides, feedback flows back) as a zero-dependency CLI: no browser, no server, no plugin, works on any diff file. It also *applies* only the approved hunks — plannotator annotates and hands the work back to the agent. |
| [diffgate](https://github.com/srbsa/diffgate) (srbsa) | Deterministic guardrail the agent runs on itself via MCP — the agent fixes its own output before it reaches disk. | diffgate's reviewer is the agent; hunkgate's reviewer is the human. Different seat, different trust model. diffgate is also Node + MCP + VS Code; hunkgate is a Python CLI with no agent integration at all. |
| [diffgate](https://pypi.org/project/diffgate/) (KozueMitarai) | Zero-dependency Python CLI that reports diff-only issues (skipped tests, removed auth, disabled cert checks) as a CI gate. | The closest cousin: same language, same zero-dep stance, same diff-first view. hunkgate adds the *decision workflow* — a persistent queue, per-hunk approve/reject with reasons, an audit log, partial apply, and the feedback prompt. diffgate reports; hunkgate gates. |
| [ReviewGate](https://github.com/dengmengmian/ReviewGate) | Pre-merge filter: screens AI code for high-risk issues, block/warn, with Claude Code / GitHub Actions integration. | ReviewGate filters and categorises; hunkgate records decisions and applies the approved subset. ReviewGate's verdict is the tool's; hunkgate's verdict is the human's. |
| [human-gate](https://pypi.org/project/human-gate/) | Human approval channel: the agent asks, the human gets a desktop notification + local web page with Approve/Deny, append-only audit log. | human-gate approves *actions* at runtime (commands the agent is about to run), over a local web server. hunkgate reviews *diffs* after the work is done, in the terminal, with per-hunk granularity and partial apply. Complementary, not overlapping. |
| [agent-gates](https://www.npmjs.com/package/@cniska/agent-gates) | Git hooks + GitHub workflows that refuse bad commits locally and in CI (bad subject, added secret, unpinned action). | Hooks enforce rules at commit time; hunkgate is the review *before* the commit exists. A hook cannot ask "should this hunk land?" — it can only refuse the whole commit. |
| [git-hunk](https://pypi.org/project/git-hunk/) | Non-interactive `git add -p`: stage/unstage hunks by stable id. | git-hunk stages hunks; hunkgate *judges* them. Staging is a git operation; approving is a human decision with a reason on the record. |
| [hunk](https://github.com/modem-dev/hunk) (modem-dev) | Review-first terminal diff viewer (TUI) for agent-authored changesets. | hunk is a *viewer*: it shows the diff beautifully. hunkgate is a *gate*: it scores, queues, records decisions, applies the approved subset and writes the feedback prompt. If you want to look, use hunk; if you want to decide, use hunkgate. They pair well. |
| [AgentGate](https://github.com/Krako-Labs/kora-agentgate) (Krako Labs) | Executable completion gate: verification contracts + Claude Code Stop Hook, runs declared checks and returns a verdict. | AgentGate verifies *completion* ("did the declared checks pass?"). hunkgate verifies *the change itself* ("should this diff land?"). Different question, different moment. |

## The rule of thumb

- The **agent** should fix its own output → diffgate (srbsa).
- A **hook** should refuse a bad commit → agent-gates.
- A **human** should decide, hunk by hunk, and apply only what they
  approved → hunkgate.
