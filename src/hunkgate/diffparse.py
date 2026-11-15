"""Parse unified diffs into a small, typed model.

Only the subset of unified diff that ``git diff`` and ``git format-patch``
produce is supported — which is the whole point: the parser is strict
about hunk headers and line counts, and refuses malformed input instead
of guessing.

Model::

    Diff
      files: list[DiffFile]
    DiffFile
      old_path, new_path, status ("added" | "deleted" | "modified" | "renamed"),
      binary: bool, hunks: list[Hunk]
    Hunk
      old_start, old_count, new_start, new_count, section (after @@),
      lines: list[DiffLine]
    DiffLine
      kind ("context" | "add" | "del"), text, new_no (line number in the
      new file, or None for deletions/context before counting)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import DiffParseError

_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: (.*))?$"
)
_GIT_DIFF_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")


@dataclass
class DiffLine:
    kind: str  # "context" | "add" | "del"
    text: str
    new_no: int | None = None
    old_no: int | None = None


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str = ""
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def added(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "add"]

    @property
    def removed(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "del"]

    @property
    def header(self) -> str:
        """Canonical ``@@`` header for this hunk (used when rebuilding patches)."""
        old = f"{self.old_start}" if self.old_count == 1 else f"{self.old_start},{self.old_count}"
        new = f"{self.new_start}" if self.new_count == 1 else f"{self.new_start},{self.new_count}"
        tail = f" {self.section}" if self.section else ""
        return f"@@ -{old} +{new} @@{tail}"


@dataclass
class DiffFile:
    old_path: str
    new_path: str
    status: str = "modified"  # added | deleted | modified | renamed
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The path a reviewer cares about: the new path, unless deleted."""
        return self.old_path if self.status == "deleted" else self.new_path

    @property
    def is_new_or_deleted(self) -> bool:
        return self.status in ("added", "deleted")


@dataclass
class Diff:
    files: list[DiffFile] = field(default_factory=list)

    @property
    def hunks(self) -> list[tuple[DiffFile, Hunk]]:
        out = []
        for f in self.files:
            for h in f.hunks:
                out.append((f, h))
        return out

    @property
    def total_hunks(self) -> int:
        return sum(len(f.hunks) for f in self.files)

    @property
    def total_added(self) -> int:
        return sum(len(h.added) for _, h in self.hunks)

    @property
    def total_removed(self) -> int:
        return sum(len(h.removed) for _, h in self.hunks)


def _strip_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def parse_diff(text: str) -> Diff:
    """Parse unified diff text. Raises DiffParseError on malformed input."""
    if not text.strip():
        raise DiffParseError("empty diff: nothing to review")
    lines = text.splitlines()
    diff = Diff()
    current: DiffFile | None = None
    hunk: Hunk | None = None
    old_no = new_no = 0
    seen_any_file = False

    def finish_hunk() -> None:
        nonlocal hunk
        if hunk is not None:
            got_old = sum(1 for ln in hunk.lines if ln.kind in ("context", "del"))
            got_new = sum(1 for ln in hunk.lines if ln.kind in ("context", "add"))
            if got_old != hunk.old_count or got_new != hunk.new_count:
                raise DiffParseError(
                    f"hunk @@ -{hunk.old_start},{hunk.old_count} "
                    f"+{hunk.new_start},{hunk.new_count} @@ has "
                    f"{got_old} old / {got_new} new lines, "
                    f"expected {hunk.old_count} / {hunk.new_count}"
                )
        hunk = None

    for raw in lines:
        m = _GIT_DIFF_RE.match(raw)
        if m:
            finish_hunk()
            current = DiffFile(old_path=_strip_prefix(m.group(1)),
                               new_path=_strip_prefix(m.group(2)))
            diff.files.append(current)
            seen_any_file = True
            continue
        if current is None:
            # Allow a bare diff without "diff --git" headers (e.g. piped
            # from `git diff --no-prefix` or hand-written patches) as long
            # as it starts with ---/+++ headers.
            if raw.startswith("--- "):
                current = DiffFile(old_path="", new_path="")
                diff.files.append(current)
                seen_any_file = True
            else:
                raise DiffParseError(
                    f"unexpected line before any file header: {raw[:80]!r}")
        if raw.startswith("--- "):
            finish_hunk()
            path = raw[4:].strip()
            if path not in ("/dev/null", ""):
                current.old_path = _strip_prefix(path)
            continue
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            if path not in ("/dev/null", ""):
                current.new_path = _strip_prefix(path)
            continue
        if raw.startswith("new file mode"):
            current.status = "added"
            continue
        if raw.startswith("deleted file mode"):
            current.status = "deleted"
            continue
        if raw.startswith("rename from "):
            current.status = "renamed"
            current.old_path = raw[len("rename from "):].strip()
            continue
        if raw.startswith("rename to "):
            current.new_path = raw[len("rename to "):].strip()
            continue
        if raw.startswith("Binary files ") and raw.rstrip().endswith(" differ"):
            current.binary = True
            continue
        if raw.startswith("index ") or raw.startswith("old mode") or raw.startswith("new mode") \
                or raw.startswith("similarity index") or raw.startswith("dissimilarity index"):
            continue
        hm = _HUNK_RE.match(raw)
        if hm:
            finish_hunk()
            old_start = int(hm.group(1))
            old_count = int(hm.group(2)) if hm.group(2) is not None else 1
            new_start = int(hm.group(3))
            new_count = int(hm.group(4)) if hm.group(4) is not None else 1
            hunk = Hunk(old_start=old_start, old_count=old_count,
                        new_start=new_start, new_count=new_count,
                        section=hm.group(5) or "")
            current.hunks.append(hunk)
            old_no, new_no = old_start, new_start
            continue
        if hunk is not None and raw[:1] in (" ", "+", "-"):
            kind = {" ": "context", "+": "add", "-": "del"}[raw[0]]
            line = DiffLine(kind=kind, text=raw[1:])
            if kind in ("context", "del"):
                line.old_no = old_no
                old_no += 1
            if kind in ("context", "add"):
                line.new_no = new_no
                new_no += 1
            hunk.lines.append(line)
            continue
        if hunk is not None and raw.startswith("\\ "):
            # "\ No newline at end of file" — marker, not content.
            continue
        if hunk is None and raw.strip() == "":
            continue
        raise DiffParseError(f"cannot parse diff line: {raw[:100]!r}")
    finish_hunk()

    if not seen_any_file or not diff.files:
        raise DiffParseError("no file headers found in diff")
    for f in diff.files:
        if not f.hunks and not f.binary:
            raise DiffParseError(f"file {f.path or '?'} has no hunks and is not binary")
    return diff


def hunk_id(diff_file: DiffFile, hunk: Hunk, file_index: int, hunk_index: int) -> str:
    """Stable, human-readable hunk id: ``F<file>.<hunk>`` (1-based)."""
    return f"F{file_index + 1}.{hunk_index + 1}"
