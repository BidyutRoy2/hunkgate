"""Review reports: Markdown, JSON and dark-mode-aware HTML.

A report answers three questions in order: what was the risk, what did
the human decide, and is the gate open or closed? Everything in it is
derived from the stored item — a report never re-scores the diff, so
the numbers in the report always match the numbers in ``show``.
"""

from __future__ import annotations

import html
import json

from .scoring import band, verdict

_BAND_LABEL = {"BLOCK": "BLOCK", "REVIEW": "REVIEW", "OK": "OK"}


def _hunk_rows(item: dict) -> list[dict]:
    rows = []
    for file_entry in item["files"]:
        for hunk in file_entry["hunks"]:
            rows.append({
                "id": hunk["id"], "path": file_entry["path"],
                "status": file_entry["status"],
                "score": hunk["score"], "band": hunk["band"],
                "decision": hunk["decision"],
                "by": hunk.get("decision_by", ""),
                "reason": hunk.get("decision_reason", ""),
                "findings": hunk["findings"],
                "added": sum(1 for ln in hunk["lines"] if ln["kind"] == "add"),
                "removed": sum(1 for ln in hunk["lines"] if ln["kind"] == "del"),
            })
    return rows


def report_data(item: dict, audit: list[dict] | None = None) -> dict:
    rows = _hunk_rows(item)
    verdict_data = verdict([{"score": r["score"], "decision": r["decision"]}
                            for r in rows])
    total_findings = sum(len(r["findings"]) for r in rows)
    return {
        "id": item["id"],
        "title": item["title"],
        "created": item["created"],
        "source": item["source"],
        "agent": item.get("agent", ""),
        "risk": max((r["score"] for r in rows), default=0),
        "files": len(item["files"]),
        "hunks": len(rows),
        "findings": total_findings,
        "item_findings": item.get("item_findings", []),
        "verdict": verdict_data,
        "rows": rows,
        "comments": item.get("comments", []),
        "audit": audit or [],
    }


def to_json(item: dict, audit: list[dict] | None = None) -> str:
    return json.dumps(report_data(item, audit), indent=2, ensure_ascii=False)


def to_markdown(item: dict, audit: list[dict] | None = None) -> str:
    data = report_data(item, audit)
    v = data["verdict"]
    lines = [
        f"# Review report — {data['id']}",
        "",
        f"**{data['title']}** · created {data['created']} · source `{data['source']}`",
        "",
        f"Risk: **{data['risk']}/100 ({band(data['risk'])})** · "
        f"Files: {data['files']} · Hunks: {data['hunks']} · "
        f"Findings: {data['findings']}",
        "",
        f"Gate: **{v['state']}** — coverage {v['coverage']}% "
        f"({v['decided']}/{v['total']} hunks decided, "
        f"{v['approved']} approved, {v['rejected']} rejected, "
        f"{v['undecided']} undecided, {v['undecided_block']} blocking)",
        "",
    ]
    if data["item_findings"]:
        lines.append("## Item-level findings")
        lines.append("")
        for finding in data["item_findings"]:
            lines.append(f"- [{finding['rule_id']}] {finding['message']} — {finding['fix']}")
        lines.append("")
    lines.append("## Hunks")
    lines.append("")
    lines.append("| Hunk | File | Risk | Decision | Findings |")
    lines.append("|---|---|---|---|---|")
    for row in data["rows"]:
        findings = ", ".join(f["rule_id"] for f in row["findings"]) or "—"
        lines.append(f"| {row['id']} | `{row['path']}` | {row['score']} ({row['band']}) "
                     f"| {row['decision']} | {findings} |")
    lines.append("")
    for row in data["rows"]:
        if not row["findings"]:
            continue
        lines.append(f"### {row['id']} · `{row['path']}` — {row['score']}/100 {row['band']}")
        lines.append("")
        for finding in row["findings"]:
            lines.append(f"- **[{finding['rule_id']}]** {finding['message']}")
            if finding["evidence"]:
                lines.append(f"  - Evidence: `{finding['evidence']}`")
            lines.append(f"  - Fix: {finding['fix']}")
        if row["reason"]:
            lines.append(f"- Decision reason: {row['reason']}")
        lines.append("")
    if data["audit"]:
        lines.append("## Audit trail")
        lines.append("")
        for event in data["audit"]:
            lines.append(f"- {event.get('at', '')} · {event.get('event', '')} · "
                         f"{event.get('hunk', event.get('item', ''))} · "
                         f"{event.get('by', '')} "
                         f"{('— ' + event['reason']) if event.get('reason') else ''}")
        lines.append("")
    return "\n".join(lines)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>hunkgate report — {id}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  margin: 2rem auto; max-width: 860px; padding: 0 1rem; line-height: 1.5;
  background: #fff; color: #111; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #0d1117; color: #e6edf3; }}
  table, th, td {{ border-color: #30363d !important; }}
  code {{ background: #161b22 !important; }}
}}
h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 1.6rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #d0d7de; padding: 0.4rem 0.6rem;
  text-align: left; font-size: 0.9rem; }}
code {{ background: #f6f8fa; padding: 0.1rem 0.3rem; border-radius: 4px; }}
.badge {{ display: inline-block; padding: 0.1rem 0.5rem; border-radius: 999px;
  font-weight: 600; font-size: 0.85rem; }}
.block {{ background: #ffebe9; color: #82071e; }}
.review {{ background: #fff8c5; color: #7a4a00; }}
.ok {{ background: #dafbe1; color: #116329; }}
@media (prefers-color-scheme: dark) {{
  .block {{ background: #5a1a1a; color: #ffb3ab; }}
  .review {{ background: #5a4a12; color: #ffe9a8; }}
  .ok {{ background: #123d1f; color: #9be8ae; }}
}}
</style></head><body>
<h1>Review report — {id}</h1>
<p><strong>{title}</strong> · created {created} · source <code>{source}</code></p>
<p>Risk: <strong>{risk}/100</strong>
<span class="badge {band_class}">{band}</span> ·
Files: {files} · Hunks: {hunks} · Findings: {findings}</p>
<p>Gate: <strong>{state}</strong> — coverage {coverage}% ({decided}/{total} decided,
{approved} approved, {rejected} rejected, {undecided} undecided,
{undecided_block} blocking)</p>
{body}
</body></html>
"""


def to_html(item: dict, audit: list[dict] | None = None) -> str:
    data = report_data(item, audit)
    v = data["verdict"]
    parts = []
    if data["item_findings"]:
        parts.append("<h2>Item-level findings</h2><ul>")
        for finding in data["item_findings"]:
            parts.append(f"<li><strong>[{html.escape(finding['rule_id'])}]</strong> "
                         f"{html.escape(finding['message'])} — "
                         f"{html.escape(finding['fix'])}</li>")
        parts.append("</ul>")
    parts.append("<h2>Hunks</h2><table><tr><th>Hunk</th><th>File</th>"
                 "<th>Risk</th><th>Decision</th><th>Findings</th></tr>")
    for row in data["rows"]:
        findings = ", ".join(html.escape(f["rule_id"]) for f in row["findings"]) or "—"
        parts.append(f"<tr><td>{row['id']}</td><td><code>{html.escape(row['path'])}</code></td>"
                     f"<td>{row['score']} ({row['band']})</td>"
                     f"<td>{html.escape(row['decision'])}</td><td>{findings}</td></tr>")
    parts.append("</table>")
    for row in data["rows"]:
        if not row["findings"]:
            continue
        parts.append(f"<h2>{row['id']} · <code>{html.escape(row['path'])}</code> — "
                     f"{row['score']}/100 {row['band']}</h2><ul>")
        for finding in row["findings"]:
            parts.append(f"<li><strong>[{html.escape(finding['rule_id'])}]</strong> "
                         f"{html.escape(finding['message'])}")
            if finding["evidence"]:
                parts.append(f"<br>Evidence: <code>{html.escape(finding['evidence'])}</code>")
            parts.append(f"<br>Fix: {html.escape(finding['fix'])}</li>")
        if row["reason"]:
            parts.append(f"<li>Decision reason: {html.escape(row['reason'])}</li>")
        parts.append("</ul>")
    if data["audit"]:
        parts.append("<h2>Audit trail</h2><ul>")
        for event in data["audit"]:
            reason = f" — {html.escape(event['reason'])}" if event.get("reason") else ""
            parts.append(f"<li>{html.escape(event.get('at', ''))} · "
                         f"{html.escape(event.get('event', ''))} · "
                         f"{html.escape(event.get('hunk', event.get('item', '')))} · "
                         f"{html.escape(event.get('by', ''))}{reason}</li>")
        parts.append("</ul>")
    return _HTML_TEMPLATE.format(
        id=html.escape(data["id"]), title=html.escape(data["title"]),
        created=html.escape(data["created"]), source=html.escape(data["source"]),
        risk=data["risk"], band=band(data["risk"]),
        band_class=band(data["risk"]).lower(),
        files=data["files"], hunks=data["hunks"], findings=data["findings"],
        state=v["state"], coverage=v["coverage"], decided=v["decided"],
        total=v["total"], approved=v["approved"], rejected=v["rejected"],
        undecided=v["undecided"], undecided_block=v["undecided_block"],
        body="\n".join(parts))
