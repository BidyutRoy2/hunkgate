"""Build an approved-only patch from a review item.

The operation is pure text: take the stored hunks, keep the ones the
human approved (or auto-approved), drop the rest, and recompute the
``@@`` headers so ``git apply`` accepts the result.

Header recomputation rules (unified diff, per file):

* ``old_start`` never changes — the old file is the same file.
* ``new_start`` shifts by the net line delta of every *dropped* hunk
  that came before it (net = new_count - old_count of the dropped hunk).
* A file with no approved hunks is dropped entirely.
* New/deleted files are all-or-nothing (the store enforces this at
  decision time); a partially-approved new file is refused here too,
  as a second line of defence.

``git apply`` still validates the result: if a kept hunk's context no
longer matches because a dropped hunk changed neighbouring lines,
``git apply --check`` fails and ``apply`` reports the failure instead
of writing a half-applied tree. That is the honest behaviour — a
partial apply that silently mis-applies would be worse than refusing.
"""

from __future__ import annotations

import subprocess

from .diffparse import DiffFile, DiffLine, Hunk, parse_diff
from .errors import HunkgateError


def _hunk_text(hunk: Hunk) -> list[str]:
    out = [hunk.header]
    for line in hunk.lines:
        prefix = {"context": " ", "add": "+", "del": "-"}[line.kind]
        out.append(prefix + line.text)
    return out


def _file_header(diff_file: DiffFile) -> list[str]:
    old = "/dev/null" if diff_file.status == "added" else f"a/{diff_file.old_path}"
    new = "/dev/null" if diff_file.status == "deleted" else f"b/{diff_file.new_path}"
    header = [f"diff --git a/{diff_file.old_path} b/{diff_file.new_path}",
              f"--- {old}", f"+++ {new}"]
    if diff_file.status == "added":
        header.insert(1, "new file mode 100644")
    if diff_file.status == "deleted":
        header.insert(1, "deleted file mode 100644")
    return header


def approved_patch(diff_text: str, approved: set[str]) -> str:
    """Return a patch containing only the approved hunks.

    ``approved`` holds hunk ids (``F1.2``) in the same order the parser
    produces them. Raises HunkgateError on a partially-approved
    new/deleted file.
    """
    diff = parse_diff(diff_text)
    out: list[str] = []
    for fi, diff_file in enumerate(diff.files):
        kept: list[tuple[int, Hunk]] = []  # (original index, hunk)
        shift = 0  # net new-file line shift from dropped hunks so far
        for hi, hunk in enumerate(diff_file.hunks):
            hid = f"F{fi + 1}.{hi + 1}"
            if hid in approved:
                new_hunk = Hunk(
                    old_start=hunk.old_start, old_count=hunk.old_count,
                    new_start=hunk.new_start - shift,
                    new_count=hunk.new_count, section=hunk.section,
                    lines=[DiffLine(kind=ln.kind, text=ln.text,
                                    new_no=ln.new_no, old_no=ln.old_no)
                           for ln in hunk.lines])
                kept.append((hi, new_hunk))
            else:
                shift += hunk.new_count - hunk.old_count
        if not kept:
            continue
        if diff_file.is_new_or_deleted and len(kept) != len(diff_file.hunks):
            raise HunkgateError(
                f"{diff_file.path}: new/deleted files are all-or-nothing — "
                f"{len(kept)} of {len(diff_file.hunks)} hunks approved")
        out.extend(_file_header(diff_file))
        for _, hunk in kept:
            out.extend(_hunk_text(hunk))
    return "\n".join(out) + ("\n" if out else "")


def approved_hunk_ids(item: dict) -> set[str]:
    return {h["id"] for f in item["files"] for h in f["hunks"]
            if h["decision"] in ("approved", "auto-approved")}


def check_applies(patch_text: str, repo: str) -> tuple[bool, str]:
    """Run ``git apply --check`` in ``repo``. Returns (ok, stderr)."""
    if not patch_text.strip():
        return False, "approved patch is empty (nothing approved yet)"
    proc = subprocess.run(
        ["git", "apply", "--check", "-"],
        input=patch_text, text=True, capture_output=True, cwd=repo)
    return proc.returncode == 0, proc.stderr.strip()


def apply_patch(patch_text: str, repo: str) -> tuple[bool, str]:
    """Run ``git apply`` in ``repo``. Returns (ok, stderr)."""
    proc = subprocess.run(
        ["git", "apply", "-"],
        input=patch_text, text=True, capture_output=True, cwd=repo)
    return proc.returncode == 0, proc.stderr.strip()
