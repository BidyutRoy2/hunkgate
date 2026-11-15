"""Tests for the unified-diff parser."""

import unittest

from hunkgate.diffparse import parse_diff
from hunkgate.errors import DiffParseError

SIMPLE = """diff --git a/src/a.py b/src/a.py
index 1111111..2222222 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,5 @@
 line one
 line two
+added line
+another added
 line three
"""

NEW_FILE = """diff --git a/src/new.py b/src/new.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1,2 @@
+first
+second
"""

DELETED = """diff --git a/src/old.py b/src/old.py
deleted file mode 100644
index 1234567..0000000
--- a/src/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-gone one
-gone two
"""

MULTI_HUNK = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1,2 +1,3 @@ def top():
 top
+middle
 bottom
@@ -10,2 +11,3 @@ def bottom():
 ten
+eleven
 twelve
"""

BINARY = """diff --git a/img/logo.png b/img/logo.png
index 1111111..2222222 100644
Binary files a/img/logo.png and b/img/logo.png differ
"""

RENAME = """diff --git a/src/old.py b/src/new.py
similarity index 90%
rename from src/old.py
rename to src/new.py
--- a/src/old.py
+++ b/src/new.py
@@ -1,2 +1,2 @@
 same
-changed
+changed now
"""

NO_NEWLINE = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1,1 +1,1 @@
-old
\\ No newline at end of file
+new
\\ No newline at end of file
"""

BARE = """--- a/src/a.py
+++ b/src/a.py
@@ -1,1 +1,2 @@
 one
+two
"""


class TestParseDiff(unittest.TestCase):
    def test_simple(self):
        diff = parse_diff(SIMPLE)
        self.assertEqual(len(diff.files), 1)
        self.assertEqual(diff.files[0].path, "src/a.py")
        self.assertEqual(diff.files[0].status, "modified")
        hunk = diff.files[0].hunks[0]
        self.assertEqual((hunk.old_start, hunk.old_count), (1, 3))
        self.assertEqual((hunk.new_start, hunk.new_count), (1, 5))
        self.assertEqual(len(hunk.added), 2)
        self.assertEqual(hunk.added[0].text, "added line")
        self.assertEqual(hunk.added[0].new_no, 3)
        self.assertEqual(hunk.added[1].new_no, 4)
        self.assertEqual(diff.total_added, 2)

    def test_new_file(self):
        diff = parse_diff(NEW_FILE)
        self.assertEqual(diff.files[0].status, "added")
        self.assertEqual(diff.files[0].path, "src/new.py")
        hunk = diff.files[0].hunks[0]
        self.assertEqual((hunk.old_start, hunk.old_count), (0, 0))
        self.assertEqual([ln.text for ln in hunk.added], ["first", "second"])

    def test_deleted_file(self):
        diff = parse_diff(DELETED)
        self.assertEqual(diff.files[0].status, "deleted")
        self.assertEqual(diff.files[0].path, "src/old.py")
        self.assertEqual(diff.total_removed, 2)

    def test_multi_hunk(self):
        diff = parse_diff(MULTI_HUNK)
        self.assertEqual(len(diff.files[0].hunks), 2)
        self.assertEqual(diff.files[0].hunks[1].section, "def bottom():")

    def test_binary(self):
        diff = parse_diff(BINARY)
        self.assertTrue(diff.files[0].binary)
        self.assertEqual(diff.total_hunks, 0)

    def test_rename(self):
        diff = parse_diff(RENAME)
        self.assertEqual(diff.files[0].status, "renamed")
        self.assertEqual(diff.files[0].old_path, "src/old.py")
        self.assertEqual(diff.files[0].new_path, "src/new.py")

    def test_no_newline_marker_ignored(self):
        diff = parse_diff(NO_NEWLINE)
        self.assertEqual(diff.total_added, 1)
        self.assertEqual(diff.total_removed, 1)

    def test_bare_diff_without_git_header(self):
        diff = parse_diff(BARE)
        self.assertEqual(len(diff.files), 1)
        self.assertEqual(diff.files[0].path, "src/a.py")

    def test_empty_diff_rejected(self):
        with self.assertRaises(DiffParseError):
            parse_diff("")

    def test_garbage_rejected(self):
        with self.assertRaises(DiffParseError):
            parse_diff("hello world\nthis is not a diff\n")

    def test_wrong_line_counts_rejected(self):
        bad = SIMPLE.replace("@@ -1,3 +1,5 @@", "@@ -1,3 +1,9 @@")
        with self.assertRaises(DiffParseError):
            parse_diff(bad)

    def test_hunk_header_roundtrip(self):
        diff = parse_diff(SIMPLE)
        self.assertEqual(diff.files[0].hunks[0].header, "@@ -1,3 +1,5 @@")
        diff2 = parse_diff(MULTI_HUNK)
        self.assertEqual(diff2.files[0].hunks[1].header,
                         "@@ -10,2 +11,3 @@ def bottom():")


if __name__ == "__main__":
    unittest.main()
