"""Tests for the CLI and the config file."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hunkgate.cli import build_parser, main
from hunkgate.config import Config, load_config
from hunkgate.demo import DEMO_DIFF
from hunkgate.errors import HunkgateError


class CliTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.orig = os.getcwd()
        os.chdir(self.cwd)

    def tearDown(self):
        os.chdir(self.orig)
        self.tmp.cleanup()

    def run_cli(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()


class TestCliFlow(CliTestBase):
    def test_full_flow_end_to_end(self):
        diff_path = self.cwd / "changes.diff"
        diff_path.write_text(DEMO_DIFF, encoding="utf-8")
        code, out = self.run_cli(["init"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["capture", "--file", str(diff_path),
                                  "--agent", "claude-code", "--title", "demo",
                                  "--auto-approve", "docs-only"])
        self.assertEqual(code, 0)
        self.assertIn("95/100", out)
        code, out = self.run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn("BLOCK", out)
        item_id = out.split()[0]
        code, out = self.run_cli(["show", item_id])
        self.assertEqual(code, 0)
        self.assertIn("SEC-01", out)
        # ci must fail while BLOCK hunks are undecided
        code, out = self.run_cli(["ci", item_id])
        self.assertEqual(code, 2)
        # reject without a reason is refused
        code, out = self.run_cli(["reject", item_id, "F1.1"])
        self.assertEqual(code, 1)
        code, out = self.run_cli(["reject", item_id, "F1.1",
                                  "--reason", "secret + verify=False"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["reject", item_id, "F2.1",
                                  "--reason", "DROP TABLE"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["reject", item_id, "F3.1",
                                  "--reason", "eval()"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["approve", item_id, "F4.1",
                                  "--reason", "skip tracked"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["ci", item_id])
        self.assertEqual(code, 0)
        self.assertIn("READY", out)
        code, out = self.run_cli(["feedback", item_id])
        self.assertEqual(code, 0)
        self.assertIn("Rejected", out)
        code, out = self.run_cli(["report", item_id, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"]["state"], "READY")

    def test_capture_from_stdin(self):
        import sys
        self.run_cli(["init"])
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")  # empty stdin is not a diff
        try:
            code, out = self.run_cli(["capture", "--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)

    def test_show_missing_item(self):
        self.run_cli(["init"])
        code, out = self.run_cli(["show", "HG-20000101-000000-abcdef"])
        self.assertEqual(code, 1)

    def test_doctor_reports_missing_store(self):
        code, out = self.run_cli(["doctor"])
        self.assertEqual(code, 1)
        self.assertIn("MISSING", out)
        self.run_cli(["init"])
        code, out = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("all good", out)

    def test_rules_lists_all(self):
        code, out = self.run_cli(["rules"])
        self.assertEqual(code, 0)
        self.assertIn("SEC-01", out)
        self.assertIn("DESTRUCT-02", out)

    def test_demo_runs(self):
        code, out = self.run_cli(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("gate READY", out)

    def test_version(self):
        with self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)


class TestConfig(unittest.TestCase):
    def _write(self, text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        tmp.write(text)
        tmp.close()
        return tmp.name

    def test_defaults(self):
        config = Config.defaults()
        self.assertEqual(config.reviewer, "")
        self.assertEqual(config.auto_approve, [])

    def test_full_config(self):
        path = self._write(
            'reviewer = "ada"\n'
            'auto_approve = ["docs-only"]\n'
            '[rules.SEC-01]\n'
            'enabled = false\n'
            '[[custom_rule]]\n'
            'id = "ACME-01"\n'
            'severity = "high"\n'
            'pattern = "TODO\\\\(acme\\\\)"\n'
            'message = "ACME TODO left in code"\n'
            'fix = "Resolve it."\n'
            'direction = "add"\n')
        config = load_config(path)
        self.assertEqual(config.reviewer, "ada")
        self.assertEqual(config.auto_approve, ["docs-only"])
        self.assertIn("SEC-01", config.disabled_rules)
        self.assertEqual(len(config.custom_rules), 1)
        rule = config.custom_rules[0].to_rule()
        self.assertEqual(rule.rule_id, "ACME-01")

    def test_bad_policy_rejected(self):
        path = self._write('auto_approve = ["everything"]\n')
        with self.assertRaises(HunkgateError):
            load_config(path)

    def test_bad_regex_rejected(self):
        path = self._write(
            '[[custom_rule]]\n'
            'id = "X-01"\nseverity = "high"\npattern = "([bad"\n'
            'message = "m"\nfix = "f"\n')
        with self.assertRaises(HunkgateError):
            load_config(path)

    def test_missing_file_rejected(self):
        with self.assertRaises(HunkgateError):
            load_config("/nonexistent/hunkgate.toml")

    def test_disabled_rule_stops_firing(self):
        from hunkgate.diffparse import parse_diff
        from hunkgate.rules import check_hunk
        text = ('diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n'
                '@@ -1,0 +1,1 @@\n+password = "hunter2-secret"\n')
        diff = parse_diff(text)
        file_entry, hunk = diff.files[0], diff.files[0].hunks[0]
        self.assertTrue(any(f.rule_id == "SEC-03"
                            for f in check_hunk(file_entry, hunk)))
        self.assertFalse(any(f.rule_id == "SEC-03"
                             for f in check_hunk(file_entry, hunk,
                                                disabled={"SEC-03"})))

    def test_custom_rule_fires(self):
        from hunkgate.diffparse import parse_diff
        from hunkgate.rules import check_hunk
        path = self._write(
            '[[custom_rule]]\n'
            'id = "ACME-01"\nseverity = "high"\npattern = "TODO\\\\(acme\\\\)"\n'
            'message = "ACME TODO"\nfix = "Resolve it."\n')
        config = load_config(path)
        rules = [r.to_rule() for r in config.custom_rules]
        text = ('diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n'
                '@@ -1,0 +1,1 @@\n+# TODO(acme): fix later\n')
        diff = parse_diff(text)
        file_entry, hunk = diff.files[0], diff.files[0].hunks[0]
        self.assertTrue(any(f.rule_id == "ACME-01"
                            for f in check_hunk(file_entry, hunk, extra=rules)))


if __name__ == "__main__":
    unittest.main()
