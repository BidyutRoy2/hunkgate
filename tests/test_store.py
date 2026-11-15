"""Tests for the store, patch filter, feedback and reports."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from hunkgate.demo import DEMO_DIFF, OLD_FILES, run_demo
from hunkgate.errors import DecisionError, ItemNotFoundError, StoreError
from hunkgate.feedback import feedback_text
from hunkgate.patchfilter import approved_hunk_ids, approved_patch
from hunkgate.report import report_data, to_json, to_markdown
from hunkgate.store import Store

SIMPLE_DIFF = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,5 @@
 one
 two
+safe line
+another safe
 three
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,1 +1,2 @@
 # title
+docs line
"""


class StoreTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / ".hunkgate")
        self.store.init()

    def tearDown(self):
        self.tmp.cleanup()


class TestStore(StoreTestBase):
    def test_init_creates_layout(self):
        self.assertTrue((Path(self.tmp.name) / ".hunkgate" / "items").is_dir())
        self.assertTrue((Path(self.tmp.name) / ".hunkgate" / "audit.jsonl").exists())

    def test_capture_and_load(self):
        item = self.store.capture(SIMPLE_DIFF, source="test", agent="codex",
                                  title="t")
        self.assertTrue(item["id"].startswith("HG-"))
        self.assertEqual(len(item["files"]), 2)
        self.assertEqual(item["files"][0]["hunks"][0]["decision"], "pending")
        loaded = self.store.load(item["id"])
        self.assertEqual(loaded["id"], item["id"])

    def test_capture_auto_approve_docs(self):
        item = self.store.capture(SIMPLE_DIFF, source="test",
                                  auto_approve=("docs-only",))
        readme_hunk = item["files"][1]["hunks"][0]
        self.assertEqual(readme_hunk["decision"], "auto-approved")
        code_hunk = item["files"][0]["hunks"][0]
        self.assertEqual(code_hunk["decision"], "pending")

    def test_load_missing_item(self):
        with self.assertRaises(ItemNotFoundError):
            self.store.load("HG-20000101-000000-abcdef")

    def test_list_items(self):
        a = self.store.capture(SIMPLE_DIFF, source="a")
        b = self.store.capture(DEMO_DIFF, source="b")
        ids = [i["id"] for i in self.store.list_items()]
        self.assertIn(a["id"], ids)
        self.assertIn(b["id"], ids)

    def test_require_store_missing(self):
        missing = Store(Path(self.tmp.name) / "nope")
        with self.assertRaises(StoreError):
            missing.capture(SIMPLE_DIFF, source="x")

    def test_approve_and_reject(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        self.store.decide(item["id"], ["F1.1"], "approved", "ada",
                          reason="looks fine")
        self.store.decide(item["id"], ["F2.1"], "rejected", "ada",
                          reason="docs claim is wrong")
        loaded = self.store.load(item["id"])
        self.assertEqual(loaded["files"][0]["hunks"][0]["decision"], "approved")
        self.assertEqual(loaded["files"][1]["hunks"][0]["decision"], "rejected")
        self.assertEqual(loaded["files"][1]["hunks"][0]["decision_reason"],
                         "docs claim is wrong")

    def test_reject_needs_reason(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        with self.assertRaises(DecisionError):
            self.store.decide(item["id"], ["F1.1"], "rejected", "ada", reason="")

    def test_approve_block_needs_reason(self):
        item = self.store.capture(DEMO_DIFF, source="test")
        with self.assertRaises(DecisionError):
            self.store.decide(item["id"], ["F1.1"], "approved", "ada", reason="")
        # With a reason it is allowed — and on the record.
        self.store.decide(item["id"], ["F1.1"], "approved", "ada",
                          reason="Key is a documented example, rotated.")
        loaded = self.store.load(item["id"])
        self.assertEqual(loaded["files"][0]["hunks"][0]["decision"], "approved")

    def test_decide_by_file_id(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        self.store.decide(item["id"], ["F1"], "approved", "ada", reason="ok")
        loaded = self.store.load(item["id"])
        self.assertEqual(loaded["files"][0]["hunks"][0]["decision"], "approved")

    def test_decide_all(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        self.store.decide(item["id"], ["all"], "rejected", "ada", reason="nope")
        loaded = self.store.load(item["id"])
        self.assertTrue(all(h["decision"] == "rejected"
                            for f in loaded["files"] for h in f["hunks"]))

    def test_decide_unknown_target(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        with self.assertRaises(DecisionError):
            self.store.decide(item["id"], ["F9.9"], "approved", "ada")

    def test_new_file_all_or_nothing(self):
        new_file = ("diff --git a/src/new.py b/src/new.py\nnew file mode 100644\n"
                    "--- /dev/null\n+++ b/src/new.py\n"
                    "@@ -0,0 +1,2 @@\n+one\n+two\n"
                    "@@ -0,0 +3,1 @@\n+three\n")
        # Two hunks in one new file: the parser accepts them; deciding one
        # must decide both.
        item = self.store.capture(new_file, source="test")
        self.store.decide(item["id"], ["F1.1"], "approved", "ada", reason="ok")
        loaded = self.store.load(item["id"])
        self.assertTrue(all(h["decision"] == "approved"
                            for h in loaded["files"][0]["hunks"]))

    def test_audit_log_append_only(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        self.store.decide(item["id"], ["F1.1"], "approved", "ada", reason="ok")
        self.store.comment(item["id"], "note", "ada")
        events = self.store.audit_log(item["id"])
        self.assertEqual([e["event"] for e in events], ["approved", "comment"])
        raw = (Path(self.tmp.name) / ".hunkgate" / "audit.jsonl").read_text()
        self.assertEqual(len(raw.strip().splitlines()), 2)

    def test_comment(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        self.store.comment(item["id"], "check the edge case", "ada")
        loaded = self.store.load(item["id"])
        self.assertEqual(loaded["comments"][0]["text"], "check the edge case")


class TestPatchFilter(StoreTestBase):
    def test_approved_only_patch_keeps_headers(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        self.store.decide(item["id"], ["F1.1"], "approved", "ada", reason="ok")
        item = self.store.load(item["id"])  # decide() rewrites the stored item
        patch = approved_patch(SIMPLE_DIFF, approved_hunk_ids(item))
        self.assertIn("src/a.py", patch)
        self.assertIn("+safe line", patch)
        self.assertNotIn("README.md", patch)
        self.assertNotIn("+docs line", patch)

    def test_empty_approval_is_empty_patch(self):
        item = self.store.capture(SIMPLE_DIFF, source="test")
        patch = approved_patch(SIMPLE_DIFF, approved_hunk_ids(item))
        self.assertEqual(patch, "")

    def test_new_file_partial_refused(self):
        new_file = ("diff --git a/src/new.py b/src/new.py\nnew file mode 100644\n"
                    "--- /dev/null\n+++ b/src/new.py\n"
                    "@@ -0,0 +1,2 @@\n+one\n+two\n"
                    "@@ -0,0 +3,1 @@\n+three\n")
        from hunkgate.errors import HunkgateError
        with self.assertRaises(HunkgateError):
            approved_patch(new_file, {"F1.1"})

    def test_apply_roundtrip_in_real_git_repo(self):
        """Approved hunks apply; rejected hunks do not land."""
        item = self.store.capture(DEMO_DIFF, source="demo",
                                  auto_approve=("docs-only",))
        self.store.decide(item["id"], ["F1.1"], "rejected", "ada",
                          reason="secret + verify=False")
        self.store.decide(item["id"], ["F2.1"], "rejected", "ada",
                          reason="DROP TABLE")
        self.store.decide(item["id"], ["F3.1"], "rejected", "ada",
                          reason="eval()")
        self.store.decide(item["id"], ["F4.1"], "approved", "ada",
                          reason="skip tracked in #12")
        item = self.store.load(item["id"])
        patch = approved_patch(DEMO_DIFF, approved_hunk_ids(item))
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        for rel, content in OLD_FILES.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        env = dict(os.environ)
        env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True,
                       env=env)
        from hunkgate.patchfilter import apply_patch, check_applies
        ok, err = check_applies(patch, str(repo))
        self.assertTrue(ok, err)
        ok, err = apply_patch(patch, str(repo))
        self.assertTrue(ok, err)
        self.assertEqual((repo / "src/auth.py").read_text(), OLD_FILES["src/auth.py"])
        self.assertEqual((repo / "src/db.py").read_text(), OLD_FILES["src/db.py"])
        self.assertEqual((repo / "src/api.py").read_text(), OLD_FILES["src/api.py"])
        self.assertIn("@pytest.mark.skip", (repo / "tests/test_api.py").read_text())
        self.assertIn("## Login", (repo / "README.md").read_text())


class TestFeedbackAndReport(StoreTestBase):
    def _decided_item(self):
        item = self.store.capture(DEMO_DIFF, source="demo",
                                  auto_approve=("docs-only",))
        self.store.decide(item["id"], ["F1.1"], "rejected", "ada",
                          reason="secret + verify=False")
        self.store.decide(item["id"], ["F2.1"], "rejected", "ada",
                          reason="DROP TABLE")
        self.store.decide(item["id"], ["F3.1"], "rejected", "ada",
                          reason="eval()")
        self.store.decide(item["id"], ["F4.1"], "approved", "ada",
                          reason="skip tracked in #12")
        return self.store.load(item["id"])

    def test_feedback_contains_reasons_and_fixes(self):
        item = self._decided_item()
        text = feedback_text(item)
        self.assertIn("secret + verify=False", text)
        self.assertIn("SEC-01", text)
        self.assertIn("Move the value to an environment variable", text)
        self.assertIn("Approved — keep as-is", text)
        self.assertIn("F4.1", text)

    def test_report_data_ready(self):
        item = self._decided_item()
        data = report_data(item, self.store.audit_log(item["id"]))
        self.assertEqual(data["verdict"]["state"], "READY")
        self.assertEqual(data["verdict"]["coverage"], 100)
        self.assertEqual(data["risk"], 95)
        self.assertEqual(data["findings"], 8)
        self.assertEqual(data["hunks"], 5)

    def test_report_markdown_and_json(self):
        item = self._decided_item()
        md = to_markdown(item)
        self.assertIn("Gate: **READY**", md)
        self.assertIn("| F1.1 | `src/auth.py` | 95 (BLOCK)", md)
        parsed = json.loads(to_json(item))
        self.assertEqual(parsed["id"], item["id"])


class TestDemo(unittest.TestCase):
    def test_demo_pinned_numbers(self):
        lines: list[str] = []
        data = run_demo(print_fn=lines.append)
        self.assertEqual(data["risk"], 95)
        self.assertEqual(data["hunks"], 5)
        self.assertEqual(data["findings"], 8)
        self.assertEqual(data["verdict"]["state"], "READY")
        self.assertEqual(data["verdict"]["coverage"], 100)
        self.assertEqual(data["verdict"]["approved"], 2)
        self.assertEqual(data["verdict"]["rejected"], 3)
        joined = "\n".join(lines)
        self.assertIn("rejected files untouched: yes", joined)
        self.assertIn("approved files updated: yes", joined)


if __name__ == "__main__":
    unittest.main()
