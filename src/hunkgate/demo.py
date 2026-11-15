"""The demo: a full review round on a fictional agent-written patch.

The fixture is a small "task-tracker" patch an agent might produce:
a login helper with a hardcoded key and TLS verification off, a
"reset" helper that wipes data and drops a table, an ``eval``-based
search filter, one skipped test, and a docs update.

Pinned outcome (the CI demo job asserts it)::

    5 files, 5 hunks, 8 findings, max risk 95/100 (BLOCK)
    F1.1 auth.py   95 BLOCK  (SEC-01 hardcoded key, AUTH-01 verify=False)
    F2.1 db.py     95 BLOCK  (DESTRUCT-01 rmtree, DESTRUCT-02 DROP TABLE)
    F3.1 api.py    75 BLOCK  (EVAL-01 eval(), NET-01 new network call)
    F4.1 test_api  40 REVIEW (TEST-01 skipped test)
    F5.1 README    10 OK     (DOC-01 docs-only, auto-approved)
    decisions: 3 rejected, 2 approved -> coverage 100%, gate READY
    apply: approved patch (F4.1 + F5.1) applies cleanly to a fresh
    checkout of the pre-diff tree; auth/db/api stay untouched.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from . import __version__
from .feedback import feedback_text
from .patchfilter import apply_patch, approved_hunk_ids, approved_patch, check_applies
from .report import report_data
from .store import Store

DEMO_DIFF = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,7 +1,11 @@
 import requests
 
+API_KEY = "sk-live-9f2c7d1a4b6e8f0a"
+
 def login(username, password):
+    session = requests.Session()
+    session.verify = False
     return {"user": username}
 
 def logout():
     return True
diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -1,4 +1,11 @@
+import shutil
 import sqlite3
 
 def connect(path):
     return sqlite3.connect(path)
+
+def reset_all():
+    shutil.rmtree("/var/lib/tracker/data")
+    conn = connect(":memory:")
+    conn.execute("DROP TABLE sessions")
+    conn.commit()
diff --git a/src/api.py b/src/api.py
--- a/src/api.py
+++ b/src/api.py
@@ -1,2 +1,7 @@
+import requests
+
 def search(items, user_filter):
-    return [i for i in items if i["name"] == user_filter]
+    return [i for i in items if eval(user_filter)]
+
+def fetch_status():
+    return requests.get("https://status.example.com/health", timeout=5)
diff --git a/tests/test_api.py b/tests/test_api.py
--- a/tests/test_api.py
+++ b/tests/test_api.py
@@ -1,4 +1,10 @@
 from api import search
 
+import pytest
+
 def test_search_exact():
     assert search([{"name": "a"}], "a") == [{"name": "a"}]
+
+@pytest.mark.skip(reason="flaky on CI, see #12")
+def test_search_case_insensitive():
+    assert search([{"name": "A"}], "a") == [{"name": "A"}]
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,3 +1,7 @@
 # task-tracker
 
 A tiny task tracker.
+
+## Login
+
+Run `tracker login` and paste your API key when asked.
"""

# The pre-diff tree: exactly the context lines of the demo diff.
OLD_FILES = {
    "src/auth.py": (
        "import requests\n"
        "\n"
        "def login(username, password):\n"
        "    return {\"user\": username}\n"
        "\n"
        "def logout():\n"
        "    return True\n"
    ),
    "src/db.py": (
        "import sqlite3\n"
        "\n"
        "def connect(path):\n"
        "    return sqlite3.connect(path)\n"
    ),
    "src/api.py": (
        "def search(items, user_filter):\n"
        "    return [i for i in items if i[\"name\"] == user_filter]\n"
    ),
    "tests/test_api.py": (
        "from api import search\n"
        "\n"
        "def test_search_exact():\n"
        "    assert search([{\"name\": \"a\"}], \"a\") == [{\"name\": \"a\"}]\n"
    ),
    "README.md": "# task-tracker\n\nA tiny task tracker.\n",
}


def _git(repo: Path, *args: str) -> None:
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "hunkgate demo", "GIT_AUTHOR_EMAIL": "demo@hunkgate.dev",
                "GIT_COMMITTER_NAME": "hunkgate demo", "GIT_COMMITTER_EMAIL": "demo@hunkgate.dev"})
    subprocess.run(["git", *args], cwd=repo, env=env,
                   capture_output=True, text=True, check=True)


def run_demo(print_fn=print) -> dict:
    """Run the demo end to end in temp dirs; return the final report data."""
    with tempfile.TemporaryDirectory(prefix="hunkgate-demo-") as tmp:
        tmp_path = Path(tmp)
        store = Store(tmp_path / ".hunkgate")
        store.init()
        item = store.capture(DEMO_DIFF, source="demo.diff", agent="claude-code",
                             title="Add login + cleanup (agent run #42)",
                             auto_approve=("docs-only",))
        item_id = item["id"]
        print_fn(f"hunkgate {__version__} — demo: {item_id}")
        print_fn(f"captured {item['title']}")
        print_fn("")
        for file_entry in item["files"]:
            for hunk in file_entry["hunks"]:
                findings = ", ".join(f["rule_id"] for f in hunk["findings"]) or "—"
                print_fn(f"  {hunk['id']}  {file_entry['path']:<20} "
                         f"{hunk['score']:>3}/100 {hunk['band']:<6} "
                         f"[{findings}]  {hunk['decision']}")
        print_fn("")
        store.decide(item_id, ["F1.1"], "rejected", "ada",
                     reason="Hardcoded API key + verify=False. Move the key "
                            "to an env var and drop verify=False.")
        store.decide(item_id, ["F2.1"], "rejected", "ada",
                     reason="DROP TABLE + rmtree in one helper. Split into a "
                            "migration with a backup plan.")
        store.decide(item_id, ["F3.1"], "rejected", "ada",
                     reason="eval() on user input. Use a parser, not eval.")
        store.decide(item_id, ["F4.1"], "approved", "ada",
                     reason="Skip is temporary and tracked in #12.")
        item = store.load(item_id)
        data = report_data(item, store.audit_log(item_id))
        verdict = data["verdict"]
        print_fn(f"decisions: {verdict['approved']} approved, "
                 f"{verdict['rejected']} rejected — "
                 f"coverage {verdict['coverage']}%, gate {verdict['state']}")
        print_fn("")
        # Apply the approved hunks to a fresh checkout of the old tree.
        repo = tmp_path / "repo"
        repo.mkdir()
        for rel, content in OLD_FILES.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "pre-agent tree")
        patch = approved_patch(DEMO_DIFF, approved_hunk_ids(item))
        ok, err = check_applies(patch, str(repo))
        print_fn(f"approved patch check: {'clean' if ok else 'FAILED: ' + err}")
        if ok:
            ok, err = apply_patch(patch, str(repo))
            print_fn(f"approved patch apply: {'done' if ok else 'FAILED: ' + err}")
            untouched = all((repo / p).read_text(encoding="utf-8") == OLD_FILES[p]
                            for p in ("src/auth.py", "src/db.py", "src/api.py"))
            changed = ("@pytest.mark.skip" in (repo / "tests/test_api.py").read_text()
                       and "## Login" in (repo / "README.md").read_text())
            print_fn(f"rejected files untouched: {'yes' if untouched else 'NO'}")
            print_fn(f"approved files updated: {'yes' if changed else 'NO'}")
        print_fn("")
        feedback = feedback_text(item, store.audit_log(item_id))
        print_fn("--- feedback prompt (first lines) ---")
        for line in feedback.splitlines()[:12]:
            print_fn(line)
        print_fn("...")
        print_fn("")
        print_fn(f"gate {verdict['state']}: {verdict['decided']}/{verdict['total']} "
                 f"hunks decided, {verdict['undecided_block']} blocking undecided")
        return data
