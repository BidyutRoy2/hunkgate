#!/usr/bin/env bash
# hunkgate demo: a full review round on the bundled fixture.
# Expected: 5 files, 5 hunks, 8 findings, max risk 95/100 (BLOCK),
# 3 rejections + 2 approvals -> coverage 100%, gate READY.
# Exit code is 0: the demo is a complete, successful review.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHONPATH=src python3 -m hunkgate demo
