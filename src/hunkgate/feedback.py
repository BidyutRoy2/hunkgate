"""Generate the feedback prompt the agent gets after a review.

The prompt is deliberately structured and copy-paste ready: the agent
receives exactly what was approved, exactly what was rejected and why,
and the human's open questions — nothing else. A rejected hunk without
a reason cannot exist (the store refuses it), so the prompt never says
"fix this" without saying what "this" is.
"""

from __future__ import annotations


def feedback_text(item: dict, audit: list[dict] | None = None) -> str:
    lines: list[str] = []
    lines.append(f"# Feedback for {item['id']} — {item['title']}")
    lines.append("")
    lines.append(f"Agent: {item.get('agent') or '(not recorded)'}  ·  "
                 f"Source: {item['source']}")
    lines.append("")
    approved, rejected, pending = [], [], []
    for file_entry in item["files"]:
        for hunk in file_entry["hunks"]:
            entry = (file_entry["path"], hunk)
            if hunk["decision"] in ("approved", "auto-approved"):
                approved.append(entry)
            elif hunk["decision"] == "rejected":
                rejected.append(entry)
            else:
                pending.append(entry)
    lines.append("## Approved — keep as-is")
    lines.append("")
    if not approved:
        lines.append("Nothing approved yet.")
    for path, hunk in approved:
        lines.append(f"- {hunk['id']} · {path} "
                     f"(lines {hunk['new_start']}+, {hunk['band']} {hunk['score']}/100)")
    lines.append("")
    lines.append("## Rejected — fix before re-submitting")
    lines.append("")
    if not rejected:
        lines.append("Nothing rejected.")
    for path, hunk in rejected:
        lines.append(f"### {hunk['id']} · {path} (lines {hunk['new_start']}+)")
        lines.append("")
        lines.append(f"Reason: {hunk['decision_reason']}")
        lines.append("")
        for finding in hunk["findings"]:
            lines.append(f"- [{finding['rule_id']}] {finding['message']}")
            lines.append(f"  Fix: {finding['fix']}")
            if finding["evidence"]:
                lines.append(f"  Evidence: `{finding['evidence']}`")
        lines.append("")
    if pending:
        lines.append("## Still undecided")
        lines.append("")
        for path, hunk in pending:
            lines.append(f"- {hunk['id']} · {path} ({hunk['band']} {hunk['score']}/100)")
        lines.append("")
    comments = item.get("comments", [])
    if comments:
        lines.append("## Reviewer notes")
        lines.append("")
        for comment in comments:
            lines.append(f"- {comment['by']}: {comment['text']}")
        lines.append("")
    lines.append("## How to re-submit")
    lines.append("")
    lines.append("1. Fix every rejected hunk above (keep the approved ones untouched).")
    lines.append("2. Produce a new diff and ask for a fresh review — do not "
                 "re-submit the old diff.")
    lines.append("3. If you disagree with a rejection, say why in your reply; "
                 "do not silently re-add the same code.")
    lines.append("")
    return "\n".join(lines)
