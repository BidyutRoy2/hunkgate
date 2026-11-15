"""hunkgate CLI — the human gate for agent-written code.

Workflow::

    hunkgate init                       # create .hunkgate/ in this repo
    git diff > changes.diff
    hunkgate capture changes.diff --agent claude-code --title "Add login"
    hunkgate list                       # the queue, riskiest first
    hunkgate show HG-...               # hunks + findings + scores
    hunkgate reject HG-... F1.1 --reason "..."     # per hunk, per file, or all
    hunkgate approve HG-... F4.1 --reason "..."    # BLOCK needs a reason
    hunkgate apply HG-...               # apply only the approved hunks
    hunkgate feedback HG-...            # copy-paste prompt back to the agent
    hunkgate report HG-... --format md  # the record
    hunkgate ci HG-...                  # exit 1 while the gate is not READY

Exit codes: 0 ok; 1 usage/decision/store error; 2 the gate is not READY
(``ci`` only).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import Config, load_config
from .demo import run_demo
from .diffparse import parse_diff
from .errors import DecisionError, HunkgateError
from .feedback import feedback_text
from .patchfilter import apply_patch, approved_hunk_ids, approved_patch, check_applies
from .report import report_data, to_html, to_json, to_markdown
from .rules import rule_table
from .scoring import band, verdict
from .store import Store

DEFAULT_STORE = ".hunkgate"


def _read_diff(args) -> tuple[str, str]:
    """Return (diff_text, source label) from --file, --stdin or git."""
    if args.file:
        path = Path(args.file)
        if not path.exists():
            raise HunkgateError(f"no such diff file: {args.file}")
        return path.read_text(encoding="utf-8"), str(path)
    if args.stdin:
        return sys.stdin.read(), "stdin"
    if args.staged:
        proc = subprocess.run(["git", "diff", "--cached"], capture_output=True,
                              text=True, cwd=args.repo or ".")
        if proc.returncode != 0:
            raise HunkgateError(f"git diff --cached failed: {proc.stderr.strip()}")
        return proc.stdout, "git diff --cached"
    if args.base:
        proc = subprocess.run(["git", "diff", args.base], capture_output=True,
                              text=True, cwd=args.repo or ".")
        if proc.returncode != 0:
            raise HunkgateError(f"git diff {args.base} failed: {proc.stderr.strip()}")
        return proc.stdout, f"git diff {args.base}"
    proc = subprocess.run(["git", "diff"], capture_output=True, text=True,
                          cwd=args.repo or ".")
    if proc.returncode != 0:
        raise HunkgateError(f"git diff failed: {proc.stderr.strip()}")
    return proc.stdout, "git diff"


def _load_config(args) -> Config:
    path = args.config
    if path is None:
        candidate = Path(".hunkgate.toml")
        if candidate.exists():
            path = str(candidate)
    if path is None:
        return Config.defaults()
    return load_config(path)


def _reviewer(args, config: Config) -> str:
    return args.reviewer or config.reviewer or os.environ.get("HUNKGATE_REVIEWER", "") \
        or os.environ.get("USER", "") or "reviewer"


def _store(args) -> Store:
    return Store(args.store or DEFAULT_STORE)


def _print_item_summary(item: dict) -> None:
    rows = [h for f in item["files"] for h in f["hunks"]]
    risk = max((h["score"] for h in rows), default=0)
    v = verdict([{"score": h["score"], "decision": h["decision"]} for h in rows])
    print(f"{item['id']}  {item['title']}")
    print(f"  risk {risk}/100 ({band(risk)})  ·  {len(item['files'])} files, "
          f"{len(rows)} hunks, {sum(len(h['findings']) for h in rows)} findings")
    print(f"  gate {v['state']} — coverage {v['coverage']}% "
          f"({v['decided']}/{v['total']} decided)")


def cmd_init(args) -> int:
    store = _store(args)
    store.init()
    print(f"review store created at {store.root}/")
    print("  items/    — one JSON file per captured diff")
    print("  audit.jsonl — append-only decision log (never edit by hand)")
    return 0


def cmd_capture(args) -> int:
    config = _load_config(args)
    diff_text, source = _read_diff(args)
    store = _store(args)
    auto = tuple(args.auto_approve) if args.auto_approve is not None \
        else tuple(config.auto_approve)
    item = store.capture(
        diff_text, source=source, agent=args.agent or "",
        title=args.title or "",
        auto_approve=auto,
        extra_rules=[r.to_rule() for r in config.custom_rules],
        disabled_rules=config.disabled_rules)
    _print_item_summary(item)
    for file_entry in item["files"]:
        for hunk in file_entry["hunks"]:
            findings = ", ".join(f["rule_id"] for f in hunk["findings"]) or "—"
            print(f"  {hunk['id']}  {file_entry['path']:<24} "
                  f"{hunk['score']:>3}/100 {hunk['band']:<6} [{findings}]  "
                  f"{hunk['decision']}")
    if item.get("item_findings"):
        print("  item-level:")
        for finding in item["item_findings"]:
            print(f"    [{finding['rule_id']}] {finding['message']}")
    return 0


def cmd_list(args) -> int:
    store = _store(args)
    items = store.list_items()
    if not items:
        print("no review items yet — run `hunkgate capture` first")
        return 0
    rows = []
    for item in items:
        hunks = [h for f in item["files"] for h in f["hunks"]]
        risk = max((h["score"] for h in hunks), default=0)
        v = verdict([{"score": h["score"], "decision": h["decision"]} for h in hunks])
        rows.append((risk, item, v))
    rows.sort(key=lambda r: (-r[0], r[1]["created"]))
    for risk, item, v in rows:
        print(f"{item['id']}  risk {risk:>3}/100 {band(risk):<6}  "
              f"gate {v['state']:<7} coverage {v['coverage']:>3}%  {item['title']}")
    return 0


def cmd_show(args) -> int:
    store = _store(args)
    item = store.load(args.item)
    _print_item_summary(item)
    for file_entry in item["files"]:
        print(f"\n{file_entry['path']} ({file_entry['status']})")
        for hunk in file_entry["hunks"]:
            print(f"  {hunk['id']}  lines {hunk['new_start']}+  "
                  f"{hunk['score']}/100 {hunk['band']}  decision: {hunk['decision']}"
                  + (f" by {hunk['decision_by']}" if hunk.get("decision_by") else "")
                  + (f" — {hunk['decision_reason']}" if hunk.get("decision_reason") else ""))
            for finding in hunk["findings"]:
                line = f"    [{finding['rule_id']}] {finding['message']}"
                if finding["line_no"]:
                    line += f" (line {finding['line_no']})"
                print(line)
                if finding["evidence"]:
                    print(f"      evidence: {finding['evidence']}")
                print(f"      fix: {finding['fix']}")
            for line in hunk["lines"]:
                prefix = {"context": " ", "add": "+", "del": "-"}[line["kind"]]
                print(f"    {prefix}{line['text']}")
    if item.get("comments"):
        print("\ncomments:")
        for comment in item["comments"]:
            print(f"  {comment['by']} ({comment['at']}): {comment['text']}")
    return 0


def _decide(args, action: str) -> int:
    config = _load_config(args)
    store = _store(args)
    reviewer = _reviewer(args, config)
    item = store.decide(args.item, args.targets, action, reviewer,
                        reason=args.reason or "")
    print(f"{action}: {', '.join(args.targets)} on {item['id']} (by {reviewer})")
    _print_item_summary(item)
    return 0


def cmd_approve(args) -> int:
    return _decide(args, "approved")


def cmd_reject(args) -> int:
    if not args.reason:
        raise DecisionError("rejecting needs a --reason (the agent cannot "
                            "fix what it cannot see)")
    return _decide(args, "rejected")


def cmd_comment(args) -> int:
    config = _load_config(args)
    store = _store(args)
    reviewer = _reviewer(args, config)
    store.comment(args.item, args.text, reviewer)
    print(f"comment added to {args.item} (by {reviewer})")
    return 0


def cmd_apply(args) -> int:
    store = _store(args)
    item = store.load(args.item)
    diff_text, _ = _read_diff_for_apply(args, item)
    patch = approved_patch(diff_text, approved_hunk_ids(item))
    if args.out:
        Path(args.out).write_text(patch, encoding="utf-8")
        print(f"approved patch written to {args.out} "
              f"({len(approved_hunk_ids(item))} hunks)")
        if args.check_only:
            return 0
    repo = args.repo or "."
    ok, err = check_applies(patch, repo)
    if not ok:
        print(f"refused: approved patch does not apply cleanly: {err}")
        print("Re-review the rejected hunks — a kept hunk probably depends "
              "on a dropped neighbour.")
        return 1
    if args.check_only:
        print("approved patch applies cleanly (check only, nothing written)")
        return 0
    ok, err = apply_patch(patch, repo)
    if not ok:
        print(f"apply failed: {err}")
        return 1
    print(f"applied {len(approved_hunk_ids(item))} approved hunks to {repo}")
    print("Rejected hunks were NOT applied — see `hunkgate feedback` "
          "for what to send back.")
    return 0


def _read_diff_for_apply(args, item: dict) -> tuple[str, str]:
    """The diff to filter: the stored one, or an explicit --file."""
    if args.file:
        return Path(args.file).read_text(encoding="utf-8"), str(args.file)
    # Rebuild the original diff from the stored item so apply never needs
    # the caller's original file.
    lines: list[str] = []
    for file_entry in item["files"]:
        old = "/dev/null" if file_entry["status"] == "added" else f"a/{file_entry['old_path']}"
        new = "/dev/null" if file_entry["status"] == "deleted" else f"b/{file_entry['new_path']}"
        lines.append(f"diff --git a/{file_entry['old_path']} b/{file_entry['new_path']}")
        if file_entry["status"] == "added":
            lines.append("new file mode 100644")
        if file_entry["status"] == "deleted":
            lines.append("deleted file mode 100644")
        lines.append(f"--- {old}")
        lines.append(f"+++ {new}")
        for hunk in file_entry["hunks"]:
            old = str(hunk["old_start"]) if hunk["old_count"] == 1 else \
                f"{hunk['old_start']},{hunk['old_count']}"
            new = str(hunk["new_start"]) if hunk["new_count"] == 1 else \
                f"{hunk['new_start']},{hunk['new_count']}"
            tail = f" {hunk['section']}" if hunk.get("section") else ""
            lines.append(f"@@ -{old} +{new} @@{tail}")
            for line in hunk["lines"]:
                prefix = {"context": " ", "add": "+", "del": "-"}[line["kind"]]
                lines.append(prefix + line["text"])
    return "\n".join(lines) + "\n", f"stored item {item['id']}"


def cmd_feedback(args) -> int:
    store = _store(args)
    item = store.load(args.item)
    text = feedback_text(item, store.audit_log(args.item))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"feedback prompt written to {args.out}")
    else:
        print(text)
    return 0


def cmd_report(args) -> int:
    store = _store(args)
    item = store.load(args.item)
    audit = store.audit_log(args.item)
    if args.format == "json":
        text = to_json(item, audit)
    elif args.format == "html":
        text = to_html(item, audit)
    else:
        text = to_markdown(item, audit)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"report written to {args.out}")
    else:
        print(text)
    return 0


def cmd_ci(args) -> int:
    store = _store(args)
    item = store.load(args.item)
    rows = [{"score": h["score"], "decision": h["decision"]}
            for f in item["files"] for h in f["hunks"]]
    v = verdict(rows)
    print(f"gate {v['state']} — coverage {v['coverage']}% "
          f"({v['decided']}/{v['total']} decided, "
          f"{v['undecided_block']} blocking undecided)")
    if v["state"] == "READY":
        return 0
    if args.allow_review and v["state"] == "REVIEW":
        return 0
    return 2


def cmd_doctor(args) -> int:
    problems: list[str] = []
    store = _store(args)
    if store.exists():
        print(f"store: {store.root}/ OK ({len(store.list_items())} items)")
    else:
        print(f"store: {store.root}/ MISSING — run `hunkgate init`")
        problems.append("store missing")
    proc = subprocess.run(["git", "--version"], capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"git: {proc.stdout.strip()} (needed for capture/apply from a repo)")
    else:
        print("git: NOT FOUND — capture from --file/--stdin still works, "
              "apply needs git")
    config = _load_config(args)
    print(f"config: reviewer={config.reviewer or '(unset)'} "
          f"auto_approve={list(config.auto_approve) or 'none'} "
          f"disabled_rules={sorted(config.disabled_rules) or 'none'} "
          f"custom_rules={len(config.custom_rules)}")
    if problems:
        print(f"doctor: {len(problems)} problem(s)")
        return 1
    print("doctor: all good")
    return 0


def cmd_rules(args) -> int:
    if args.format == "json":
        print(json.dumps(rule_table(), indent=2))
        return 0
    if args.format == "md":
        print("| Rule | Severity | What it catches |")
        print("|---|---|---|")
        for rule in rule_table():
            print(f"| {rule['rule_id']} | {rule['severity']} | {rule['message']} |")
        return 0
    for rule in rule_table():
        print(f"{rule['rule_id']:<12} {rule['severity']:<8} {rule['message']}")
    return 0


def cmd_demo(args) -> int:
    run_demo()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hunkgate",
        description="The human gate for agent-written code: review a diff "
                    "hunk by hunk, approve what you trust, apply only that.")
    parser.add_argument("--version", action="version",
                        version=f"hunkgate {__version__}")
    parser.add_argument("--store", default=None,
                        help="review store directory (default .hunkgate)")
    parser.add_argument("--config", default=None,
                        help="config file (default .hunkgate.toml if present)")
    parser.add_argument("--reviewer", default=None,
                        help="name recorded on decisions (default: config, "
                             "HUNKGATE_REVIEWER, or $USER)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the review store (.hunkgate/)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("capture", help="capture a diff as a review item")
    p.add_argument("--file", default=None, help="diff file (default: git diff)")
    p.add_argument("--stdin", action="store_true", help="read the diff from stdin")
    p.add_argument("--staged", action="store_true", help="use git diff --cached")
    p.add_argument("--base", default=None, help="use git diff <base>")
    p.add_argument("--repo", default=None, help="repo directory for git diff")
    p.add_argument("--agent", default="", help="which agent wrote this (label)")
    p.add_argument("--title", default="", help="short title for the item")
    p.add_argument("--auto-approve", nargs="*", default=None,
                   choices=["docs-only", "tests-only"],
                   help="auto-approve policy (overrides config)")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("list", help="list review items, riskiest first")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one item: hunks, findings, decisions")
    p.add_argument("item", help="item id, e.g. HG-20261115-123045-a1b2c3")
    p.set_defaults(func=cmd_show)

    for name, action, help_text in (
            ("approve", "approved", "approve hunks (BLOCK needs --reason)"),
            ("reject", "rejected", "reject hunks (needs --reason)")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("item", help="item id")
        p.add_argument("targets", nargs="+",
                       help="hunk ids (F1.2), file ids (F1), or 'all'")
        p.add_argument("--reason", default="",
                       help="why — recorded in the audit log; required for "
                            "reject and for approving BLOCK hunks")
        p.set_defaults(func=cmd_approve if name == "approve" else cmd_reject)

    p = sub.add_parser("comment", help="add a reviewer note to an item")
    p.add_argument("item", help="item id")
    p.add_argument("--text", required=True, help="the note")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("apply", help="apply only the approved hunks")
    p.add_argument("item", help="item id")
    p.add_argument("--file", default=None,
                   help="diff file to filter (default: the stored item)")
    p.add_argument("--repo", default=None, help="repo to apply in (default .)")
    p.add_argument("--out", default=None, help="also write the approved patch here")
    p.add_argument("--check-only", action="store_true",
                   help="only check that the patch applies; do not write")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("feedback", help="feedback prompt to send back to the agent")
    p.add_argument("item", help="item id")
    p.add_argument("--out", default=None, help="write to file instead of stdout")
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("report", help="review report (md, json, html)")
    p.add_argument("item", help="item id")
    p.add_argument("--format", default="md", choices=["md", "json", "html"])
    p.add_argument("--out", default=None, help="write to file instead of stdout")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("ci", help="exit 2 unless the gate is READY")
    p.add_argument("item", help="item id")
    p.add_argument("--allow-review", action="store_true",
                   help="also pass when only REVIEW/OK hunks are undecided")
    p.set_defaults(func=cmd_ci)

    p = sub.add_parser("doctor", help="check the store, git and config")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("rules", help="list the built-in risk rules")
    p.add_argument("--format", default="text", choices=["text", "json", "md"])
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("demo", help="run the bundled demo end to end")
    p.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (HunkgateError, DecisionError) as exc:
        print(f"hunkgate: error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
