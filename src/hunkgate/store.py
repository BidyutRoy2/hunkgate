"""The review store: items + append-only audit log.

Layout inside the store directory (default ``.hunkgate/``)::

    .hunkgate/
      items/
        HG-20261115-123045-a1b2c3.json   # one review item
      audit.jsonl                       # append-only decision log

An item is a plain JSON dict: metadata, the parsed diff (files, hunks,
findings, scores) and one decision per hunk. The audit log records every
decision as a separate event with a timestamp — it is the record the
team can point at later, and it is never rewritten.

Decisions per hunk: ``pending`` | ``approved`` | ``rejected`` |
``auto-approved``. Approving a BLOCK hunk requires a reason (enforced
in ``decide``), because "I looked at the secret and it is fine" is a
claim that belongs on the record.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .diffparse import Diff, hunk_id, parse_diff
from .errors import DecisionError, ItemNotFoundError, StoreError
from .rules import Finding, check_hunk, check_item
from .scoring import band, hunk_score, is_docs_only, is_tests_only


def new_item_id(diff_text: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha1(diff_text.encode("utf-8")).hexdigest()[:6]
    return f"HG-{stamp}-{digest}"


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.items_dir = self.root / "items"
        self.audit_path = self.root / "audit.jsonl"

    # -- setup -------------------------------------------------------------
    def init(self) -> None:
        self.items_dir.mkdir(parents=True, exist_ok=True)
        if not self.audit_path.exists():
            self.audit_path.write_text("", encoding="utf-8")

    def exists(self) -> bool:
        return self.items_dir.is_dir()

    def require(self) -> None:
        if not self.exists():
            raise StoreError(
                f"no review store at {self.root} — run `hunkgate init` first")

    # -- items ---------------------------------------------------------------
    def capture(self, diff_text: str, source: str, agent: str = "",
                title: str = "", auto_approve: tuple[str, ...] = (),
                extra_rules: list | None = None,
                disabled_rules: set[str] | frozenset | None = None) -> dict:
        """Parse a diff, score every hunk, store the item, return it."""
        self.require()
        diff = parse_diff(diff_text)
        item_id = new_item_id(diff_text)
        item = {
            "id": item_id,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            "agent": agent,
            "title": title or f"Review {item_id}",
            "files": [],
            "item_findings": check_item(diff)["findings"],
        }
        for fi, diff_file in enumerate(diff.files):
            entry = {
                "path": diff_file.path,
                "old_path": diff_file.old_path,
                "new_path": diff_file.new_path,
                "status": diff_file.status,
                "binary": diff_file.binary,
                "hunks": [],
            }
            for hi, hunk in enumerate(diff_file.hunks):
                findings = check_hunk(diff_file, hunk,
                                      extra=extra_rules,
                                      disabled=disabled_rules)
                score = hunk_score(findings)
                hid = hunk_id(diff_file, hunk, fi, hi)
                decision = "pending"
                decision_reason = ""
                if "docs-only" in auto_approve and is_docs_only(findings, diff_file.path):
                    decision, decision_reason = "auto-approved", "policy: docs-only"
                elif "tests-only" in auto_approve and is_tests_only(findings, diff_file.path):
                    decision, decision_reason = "auto-approved", "policy: tests-only"
                entry["hunks"].append({
                    "id": hid,
                    "old_start": hunk.old_start,
                    "old_count": hunk.old_count,
                    "new_start": hunk.new_start,
                    "new_count": hunk.new_count,
                    "section": hunk.section,
                    "lines": [{"kind": ln.kind, "text": ln.text,
                               "new_no": ln.new_no, "old_no": ln.old_no}
                              for ln in hunk.lines],
                    "findings": [f.to_dict() for f in findings],
                    "score": score,
                    "band": band(score),
                    "decision": decision,
                    "decision_by": "policy" if decision == "auto-approved" else "",
                    "decision_at": item["created"] if decision == "auto-approved" else "",
                    "decision_reason": decision_reason,
                })
            item["files"].append(entry)
        self._write_item(item)
        if any(h["decision"] == "auto-approved"
               for f in item["files"] for h in f["hunks"]):
            self._audit({"event": "auto-approve", "item": item_id,
                         "policy": list(auto_approve)})
        return item

    def _write_item(self, item: dict) -> None:
        path = self.items_dir / f"{item['id']}.json"
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    def load(self, item_id: str) -> dict:
        self.require()
        path = self.items_dir / f"{item_id}.json"
        if not path.exists():
            raise ItemNotFoundError(f"no review item {item_id} in {self.root}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_items(self) -> list[dict]:
        self.require()
        items = []
        for path in sorted(self.items_dir.glob("HG-*.json")):
            items.append(json.loads(path.read_text(encoding="utf-8")))
        return items

    # -- decisions -----------------------------------------------------------
    def decide(self, item_id: str, hunk_ids: list[str], action: str,
               reviewer: str, reason: str = "") -> dict:
        """Approve/reject hunks. Returns the updated item.

        ``hunk_ids`` may be hunk ids (``F1.2``), file ids (``F1`` = every
        hunk in that file) or ``all``. Approving a BLOCK hunk requires a
        reason; new/deleted files are decided as a whole file.
        """
        item = self.load(item_id)
        if action not in ("approved", "rejected"):
            raise DecisionError(f"unknown decision {action!r}")
        if action == "rejected" and not reason.strip():
            raise DecisionError("rejecting needs a --reason (the agent "
                                "cannot fix what it cannot see)")
        targets = self._resolve_targets(item, hunk_ids)
        if not targets:
            raise DecisionError(f"no hunks match {hunk_ids}")
        # New/deleted files are all-or-nothing: deciding one hunk decides
        # the whole file, because a partial new file is not a thing.
        expanded: list = []
        seen_ids: set = set()
        for file_entry, hunk in targets:
            hunks = file_entry["hunks"] if file_entry["status"] in ("added", "deleted") \
                else [hunk]
            for h in hunks:
                if h["id"] not in seen_ids:
                    seen_ids.add(h["id"])
                    expanded.append((file_entry, h))
        targets = expanded
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for file_entry, hunk in targets:
            if hunk["band"] == "BLOCK" and action == "approved" and not reason.strip():
                raise DecisionError(
                    f"{hunk['id']} is BLOCK ({hunk['score']}/100) — approving "
                    "it needs a --reason on the record")
            hunk["decision"] = action
            hunk["decision_by"] = reviewer
            hunk["decision_at"] = now
            hunk["decision_reason"] = reason.strip()
            self._audit({"event": action, "item": item_id, "hunk": hunk["id"],
                         "file": file_entry["path"], "by": reviewer,
                         "reason": reason.strip(), "at": now})
        self._write_item(item)
        return item

    def comment(self, item_id: str, text: str, reviewer: str) -> dict:
        item = self.load(item_id)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        item.setdefault("comments", []).append(
            {"by": reviewer, "at": now, "text": text})
        self._audit({"event": "comment", "item": item_id, "by": reviewer,
                     "text": text, "at": now})
        self._write_item(item)
        return item

    def _resolve_targets(self, item: dict, hunk_ids: list[str]):
        targets = []
        for file_entry in item["files"]:
            for hunk in file_entry["hunks"]:
                fid = hunk["id"].split(".")[0]
                if "all" in hunk_ids or hunk["id"] in hunk_ids or fid in hunk_ids:
                    targets.append((file_entry, hunk))
        # Deduplicate (e.g. F1 and F1.2 given together).
        seen, out = set(), []
        for pair in targets:
            if pair[1]["id"] not in seen:
                seen.add(pair[1]["id"])
                out.append(pair)
        return out

    # -- audit ---------------------------------------------------------------
    def _audit(self, event: dict) -> None:
        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def audit_log(self, item_id: str | None = None) -> list[dict]:
        self.require()
        events = []
        if not self.audit_path.exists():
            return events
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if item_id is None or event.get("item") == item_id:
                events.append(event)
        return events
