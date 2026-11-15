"""Test package: make the src layout importable without installing.

A bare clone must be able to run the suite with:
    python3 -m unittest discover -s tests -t .
(and with pytest, which reads pyproject.toml testpaths).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
